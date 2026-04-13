## SWE-Bench Pro

This is a forked version of the original repository, containing only the minimal code required to function as an evaluation harness.

### Building instance images and `.sif` files

The repo ships **731** evaluation instances. Each has a pair of Dockerfiles under:

- `dockerfiles/base_dockerfile/<instance_id>/Dockerfile`
- `dockerfiles/instance_dockerfile/<instance_id>/Dockerfile`

The instance Dockerfile’s first `FROM` line names the base image tag (either a local-style `base_…` name or a full registry reference such as ECR). The helper script builds the base image with that exact tag, then builds the instance image, then (by default) converts the instance image to an **Apptainer/Singularity** `.sif` using `docker-daemon://…`.

#### Prerequisites

- **Docker** (daemon running; your user can talk to it, e.g. in the `docker` group).
- **Apptainer** or **Singularity** on `PATH` if you want `.sif` output (`BUILD_SIF=1`, the default). The script picks `apptainer` if present, otherwise `singularity`.
- Enough disk space for layers and 731 `.sif` files (plan for tens to hundreds of GB depending on images).

#### Basic usage

From the repository root:

```bash
./scripts/build_instance_docker_and_sif.sh
```

- **Docker images**: tagged as `swebench-pro/<instance_id_lowercase>:latest` (Docker’s rules; IDs are lowercased only in this tag).
- **SIF files**: written to `./sifs/<instance_id>.sif` (default).
- **Logs**: one file per instance under `./build_logs/<instance_id>.log`.

#### Arm64 Dockerfiles (optional)

If you use the generated arm64-oriented tree (for example after `python scripts/generate_arm64_dockerfiles.py`):

```bash
DOCKERFILES_ROOT=dockerfiles_arm64 ./scripts/build_instance_docker_and_sif.sh
```

#### Common options (environment variables)

| Variable | Default | Meaning |
|----------|---------|---------|
| `DOCKERFILES_ROOT` | `dockerfiles` | Root containing `base_dockerfile/` and `instance_dockerfile/`. |
| `OUTPUT_DIR` | `./sifs` | Where `.sif` files are written. |
| `LOG_DIR` | `./build_logs` | Per-instance build logs. |
| `BUILD_SIF` | `1` | Set to `0` to only build Docker images (no Apptainer/Singularity step). |
| `SIF_ONLY` | `0` | Set to `1` to assume Docker images already exist; only build `.sif`. |
| `SKIP_EXISTING_SIF` | `0` | Set to `1` to skip an instance if `OUTPUT_DIR/<instance_id>.sif` already exists. |
| `SKIP_EXISTING_IMAGE` | `0` | Set to `1` to skip the instance `docker build` if `swebench-pro/<id>:latest` already exists. |
| `DEDUP_BASE` | `1` | If `1`, skip rebuilding a base image when that `FROM` image already exists locally. |
| `PARALLEL` | `1` | Number of concurrent instance jobs; values `> 1` use file locks so two jobs do not build the same base tag at once. |
| `DOCKER_BUILD_OPTS` | _(empty)_ | Extra arguments passed to every `docker build` (e.g. `--progress=plain`). |
| `SINGULARITY_BIN` | auto | Force `apptainer` or `singularity` if both exist. |
| `INSTANCE_FILTER` | `*` | Shell glob matched against **directory names** under `instance_dockerfile/` (e.g. `'*ansible*'`). |

Examples:

```bash
# Docker only (no .sif)
BUILD_SIF=0 ./scripts/build_instance_docker_and_sif.sh

# Only rebuild .sif from existing Docker images
SIF_ONLY=1 ./scripts/build_instance_docker_and_sif.sh

# Subset of instances
INSTANCE_FILTER='*tutanota*' ./scripts/build_instance_docker_and_sif.sh

# Resume .sif generation without overwriting
SKIP_EXISTING_SIF=1 ./scripts/build_instance_docker_and_sif.sh

# Parallel instance builds (use with care; still heavy on disk/CPU)
PARALLEL=4 ./scripts/build_instance_docker_and_sif.sh
```

#### Notes and limitations

- **ECR / private bases**: Instance Dockerfiles that `FROM` a full registry URL are satisfied by building the local `base_dockerfile` and tagging the result with that **same** reference so `docker build` does not need to pull that tag from AWS. You still need whatever network and credentials the **base Dockerfile** itself requires (e.g. `git clone`, package mirrors).
- **`docker-daemon://`**: Apptainer/Singularity must be able to read images from your local Docker. Some clusters require **fakeroot** or admin-approved config; adjust your environment or wrap the `singularity`/`apptainer` invocation if builds fail at the SIF step.
- **Time and size**: A full run of 731 instances is a long batch job; start with a narrow `INSTANCE_FILTER` to validate your setup.
