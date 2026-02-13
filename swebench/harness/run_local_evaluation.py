import argparse
import json
import os
import subprocess

import pandas as pd
from tqdm import tqdm


def load_base_docker(iid):
    # If these files aren't available inside the container,
    # you may need to ensure the dockerfiles directory is mounted.
    try:
        with open(f"dockerfiles/base_dockerfile/{iid}/Dockerfile") as fp:
            return fp.read()
    except FileNotFoundError:
        return ""


def instance_docker(iid):
    try:
        with open(f"dockerfiles/instance_dockerfile/{iid}/Dockerfile") as fp:
            return fp.read()
    except FileNotFoundError:
        return ""


def load_local_script(scripts_dir, instance_id, script_name):
    """Load a script file from local scripts directory."""
    script_path = os.path.join(scripts_dir, instance_id, script_name)
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Script not found: {script_path}")

    with open(script_path, "r") as f:
        return f.read()


def create_entryscript(sample, workspace_dir):
    before_repo_set_cmd = sample["before_repo_set_cmd"].strip().split("\n")[-1]
    selected_test_files_to_run = ",".join(eval(sample["selected_test_files_to_run"]))
    base_commit = sample["base_commit"]

    base_dockerfile = load_base_docker(sample["instance_id"])
    instance_dockerfile = instance_docker(sample["instance_id"])

    # Extract ENV commands to ensure the internal bash environment matches
    env_cmds = []
    for dockerfile_content in [base_dockerfile, instance_dockerfile]:
        for line in dockerfile_content.split("\n"):
            line = line.strip()
            if line.startswith("ENV"):
                env_cmd = line.replace("ENV", "export", 1)
                env_cmds.append(env_cmd)

    env_cmds = "\n".join(env_cmds)

    # We use absolute paths provided by workspace_dir
    patch_path = os.path.join(workspace_dir, "patch.diff")
    run_script_path = os.path.join(workspace_dir, "run_script.sh")
    parser_path = os.path.join(workspace_dir, "parser.py")
    stdout_path = os.path.join(workspace_dir, "stdout.log")
    stderr_path = os.path.join(workspace_dir, "stderr.log")
    output_json_path = os.path.join(workspace_dir, "output.json")
    patch_status_path = os.path.join(workspace_dir, "patch_status.txt")

    entry_script = f"""
{env_cmds}
# apply patch
cd /app
git reset --hard {base_commit}
git checkout {base_commit}
git apply -v {patch_path}
if [ $? -eq 0 ]; then
    echo "PATCH_APPLY_SUCCESS" > {patch_status_path}
else
    echo "PATCH_APPLY_FAILED" > {patch_status_path}
    exit 1
fi
{before_repo_set_cmd}
# run test
bash {run_script_path} {selected_test_files_to_run} > {stdout_path} 2> {stderr_path}
# run parsing script
python {parser_path} {stdout_path} {stderr_path} {output_json_path}
"""
    return entry_script


def prepare_run(uid, output_dir, redo):
    uid_dir = os.path.join(output_dir, uid)
    os.makedirs(uid_dir, exist_ok=True)
    output_path = os.path.join(uid_dir, "output.json")
    if not redo and os.path.exists(output_path):
        return None, output_path, os.path.join(uid_dir, "workspace")
    workspace_dir = os.path.join(uid_dir, "workspace")
    os.makedirs(workspace_dir, exist_ok=True)
    return None, output_path, workspace_dir


def assemble_workspace_files(uid, scripts_dir, patch, sample, workspace_dir):
    run_script = load_local_script(scripts_dir, uid, "run_script.sh")
    parser_script = load_local_script(scripts_dir, uid, "parser.py")
    entryscript_content = create_entryscript(sample, workspace_dir)

    files = {
        "patch.diff": patch,
        "run_script.sh": run_script,
        "parser.py": parser_script,
        "entryscript.sh": entryscript_content,
    }
    return files, entryscript_content


def write_files_local(workspace_dir, files):
    for rel_path, content in files.items():
        dst = os.path.join(workspace_dir, rel_path)
        with open(dst, "w") as f:
            f.write(content)


def collect_outputs_local(workspace_dir, output_dir, uid):
    # Transfer results from workspace to output_dir
    src_json = os.path.join(workspace_dir, "output.json")
    dest_json = os.path.join(output_dir, uid, "output.json")
    patch_status_path = os.path.join(workspace_dir, "patch_status.txt")

    patch_success = False
    if os.path.exists(patch_status_path):
        with open(patch_status_path, "r") as f:
            if "PATCH_APPLY_SUCCESS" in f.read():
                patch_success = True

    output = {"patch_successfully_applied": patch_success, "tests": []}

    if os.path.exists(src_json):
        try:
            with open(src_json, "r") as f_in:
                output.update(json.load(f_in))
        except json.JSONDecodeError:
            pass

    os.makedirs(os.path.dirname(dest_json), exist_ok=True)
    with open(dest_json, "w") as f_out:
        json.dump(output, f_out, indent=4)

    return output


def eval_internal(patch, sample, output_dir, scripts_dir, redo=False):
    """
    Executes the evaluation logic locally within the current environment
    (e.g., inside an Apptainer container).
    """
    uid = sample["instance_id"]
    _, output_path, workspace_dir = prepare_run(uid, output_dir, redo)
    workspace_dir = os.path.abspath(workspace_dir)

    try:
        # Prepare files
        files, entryscript_content = assemble_workspace_files(
            uid, scripts_dir, patch, sample, workspace_dir
        )
        write_files_local(workspace_dir, files)

        # Execute the entryscript locally via subprocess
        script_path = os.path.join(workspace_dir, "entryscript.sh")
        print(f"Executing evaluation script for {uid}...")

        result = subprocess.run(["bash", script_path], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Warning: Script for {uid} exited with code {result.returncode}")

        # Collect findings
        output = collect_outputs_local(workspace_dir, output_dir, uid)
        return output
    except Exception as e:
        print(f"Error in eval_internal for {uid}: {repr(e)}")
        return None


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run evaluation inside a container environment"
    )
    parser.add_argument("--raw_sample_path", required=True)
    parser.add_argument("--patch_path", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--scripts_dir", required=True)
    parser.add_argument("--redo", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()

    # Load data
    if args.raw_sample_path.endswith(".jsonl"):
        raw_sample_df = pd.read_json(args.raw_sample_path, lines=True)
    else:
        raw_sample_df = pd.read_csv(args.raw_sample_path)

    raw_sample_df = raw_sample_df.fillna("").set_index("instance_id", drop=False)

    with open(args.patch_path, "r") as f:
        patches_to_run = json.load(f)
        if isinstance(patches_to_run, dict):
            patches_to_run = [patches_to_run]

    for patch_sample in tqdm(patches_to_run, desc="Evaluating"):
        instance_id = patch_sample["instance_id"]
        if instance_id not in raw_sample_df.index:
            continue

        output_dir = os.path.join(args.output_dir, patch_sample["model_name_or_path"])

        eval_results = {
            instance_id: {
                "patch_is_None": False,
                "patch_exists": False,
                "patch_successfully_applied": False,
                "resolved": False,
            }
        }

        if patch_sample["model_patch"] is None:
            eval_results[instance_id]["patch_is_None"] = True
        else:
            eval_results[instance_id]["patch_exists"] = True
            output = eval_internal(
                patch_sample["model_patch"],
                raw_sample_df.loc[instance_id],
                output_dir,
                args.scripts_dir,
                redo=args.redo,
            )

            if output:
                eval_results[instance_id].update(output)
                if output["patch_successfully_applied"]:
                    passed_tests = {
                        x["name"] for x in output["tests"] if x["status"] == "PASSED"
                    }
                    raw_sample = raw_sample_df.loc[instance_id]
                    f2p = set(eval(raw_sample["fail_to_pass"]))
                    p2p = set(eval(raw_sample["pass_to_pass"]))
                    eval_results[instance_id]["resolved"] = (f2p | p2p) <= passed_tests

        with open(os.path.join(output_dir, instance_id, "report.json"), "w") as f:
            json.dump(eval_results, f, indent=4)


if __name__ == "__main__":
    main()
