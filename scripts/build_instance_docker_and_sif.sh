#!/usr/bin/env bash
# Build all 731 instance Docker images (base + instance layers) and optional .sif files.
#
# Requirements:
#   - docker (daemon running; user in docker group or root)
#   - apptainer OR singularity (only if BUILD_SIF=1, default)
#
# Typical usage from the repository root:
#   ./scripts/build_instance_docker_and_sif.sh
#   DOCKERFILES_ROOT=dockerfiles_arm64 ./scripts/build_instance_docker_and_sif.sh
#   BUILD_SIF=0 ./scripts/build_instance_docker_and_sif.sh          # Docker only
#   SIF_ONLY=1 ./scripts/build_instance_docker_and_sif.sh           # assume images exist
#   INSTANCE_FILTER='*ansible*' ./scripts/build_instance_docker_and_sif.sh
#
# Environment (optional):
#   DOCKERFILES_ROOT   default: dockerfiles  (use dockerfiles_arm64 for arm64 tree)
#   OUTPUT_DIR         default: ./sifs      (.sif files written here)
#   LOG_DIR            default: ./build_logs
#   BUILD_SIF          default: 1          (0 to skip Apptainer/Singularity)
#   SIF_ONLY           default: 0          (1 = skip docker builds, only build .sif)
#   SKIP_EXISTING_SIF  default: 0          (1 = skip if OUTPUT_DIR/<id>.sif exists)
#   SKIP_EXISTING_IMAGE default: 0       (1 = skip instance docker build if tag exists)
#   DEDUP_BASE         default: 1          (1 = do not rebuild same base FROM twice)
#   PARALLEL           default: 1          (number of concurrent instance jobs; >=2 uses flock per base tag)
#   DOCKER_BUILD_OPTS  extra args passed to every "docker build" (e.g. --progress=plain)
#   SINGULARITY_BIN    default: apptainer if on PATH, else singularity
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

DOCKERFILES_ROOT="${DOCKERFILES_ROOT:-dockerfiles}"
[[ "${DOCKERFILES_ROOT}" != /* ]] && DOCKERFILES_ROOT="${REPO_ROOT}/${DOCKERFILES_ROOT}"

OUTPUT_DIR="${OUTPUT_DIR:-${REPO_ROOT}/sifs}"
[[ "${OUTPUT_DIR}" != /* ]] && OUTPUT_DIR="${REPO_ROOT}/${OUTPUT_DIR}"

LOG_DIR="${LOG_DIR:-${REPO_ROOT}/build_logs}"
[[ "${LOG_DIR}" != /* ]] && LOG_DIR="${REPO_ROOT}/${LOG_DIR}"
BUILD_SIF="${BUILD_SIF:-1}"
SIF_ONLY="${SIF_ONLY:-0}"
SKIP_EXISTING_SIF="${SKIP_EXISTING_SIF:-0}"
SKIP_EXISTING_IMAGE="${SKIP_EXISTING_IMAGE:-0}"
DEDUP_BASE="${DEDUP_BASE:-1}"
PARALLEL="${PARALLEL:-1}"
DOCKER_BUILD_OPTS="${DOCKER_BUILD_OPTS:-}"
INSTANCE_FILTER="${INSTANCE_FILTER:-*}"

if [[ ! -d "${DOCKERFILES_ROOT}/instance_dockerfile" ]]; then
  echo "ERROR: ${DOCKERFILES_ROOT}/instance_dockerfile not found (set DOCKERFILES_ROOT or run from repo root)." >&2
  exit 1
fi

if command -v apptainer >/dev/null 2>&1; then
  SINGULARITY_BIN="${SINGULARITY_BIN:-apptainer}"
elif command -v singularity >/dev/null 2>&1; then
  SINGULARITY_BIN="${SINGULARITY_BIN:-singularity}"
else
  SINGULARITY_BIN="${SINGULARITY_BIN:-}"
fi

if [[ "${BUILD_SIF}" == "1" && "${SIF_ONLY}" == "0" && -z "${SINGULARITY_BIN}" ]]; then
  echo "WARN: Neither apptainer nor singularity found; set BUILD_SIF=0 or install one of them." >&2
fi

mkdir -p "${OUTPUT_DIR}" "${LOG_DIR}"

# First non-empty FROM line, strip leading FROM and any --platform=... tokens.
parse_from_image() {
  awk '
    /^[[:space:]]*#/ { next }
    /^[Ff][Rr][Oo][Mm][[:space:]]/ {
      line = $0
      sub(/^[Ff][Rr][Oo][Mm][[:space:]]+/, "", line)
      while (line ~ /^--platform=/) {
        sub(/^--platform=[^[:space:]]+[[:space:]]+/, "", line)
      }
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
      print line
      exit
    }
  ' "$1"
}

# Docker image tag for the final instance image (lowercase for broad daemon compatibility).
instance_docker_tag() {
  local id="$1"
  local low
  low="$(printf '%s' "${id}" | tr '[:upper:]' '[:lower:]')"
  echo "swebench-pro/${low}:latest"
}

build_one() {
  local id="$1"
  local log="${LOG_DIR}/${id}.log"
  local inst_df="${DOCKERFILES_ROOT}/instance_dockerfile/${id}/Dockerfile"
  local base_df="${DOCKERFILES_ROOT}/base_dockerfile/${id}/Dockerfile"
  local from_image
  local itag
  local lock_dir="${LOG_DIR}/.base_locks"

  mkdir -p "${lock_dir}"
  : >"${log}"

  {
    echo "==== ${id} ===="
    if [[ ! -f "${inst_df}" ]]; then
      echo "ERROR: missing ${inst_df}" >&2
      exit 1
    fi
    if [[ ! -f "${base_df}" ]]; then
      echo "ERROR: missing ${base_df}" >&2
      exit 1
    fi

    from_image="$(parse_from_image "${inst_df}")"
    if [[ -z "${from_image}" ]]; then
      echo "ERROR: could not parse FROM in ${inst_df}" >&2
      exit 1
    fi

    itag="$(instance_docker_tag "${id}")"

    if [[ "${SIF_ONLY}" == "1" ]]; then
      echo "SIF_ONLY=1: skipping docker builds for ${id}"
    else
      if [[ "${SKIP_EXISTING_IMAGE}" == "1" ]] && docker image inspect "${itag}" >/dev/null 2>&1; then
        echo "Skip instance docker build (image exists): ${itag}"
      else
        # Base image: tag must match instance Dockerfile FROM exactly.
        if [[ "${DEDUP_BASE}" == "1" ]] && docker image inspect "${from_image}" >/dev/null 2>&1; then
          echo "Reuse existing base image: ${from_image}"
        else
          echo "Build base -> ${from_image}"
          lockf="${lock_dir}/$(printf '%s' "${from_image}" | sha256sum | awk '{print $1}').lock"
          if [[ "${PARALLEL}" -gt 1 ]]; then
            (
              flock 9
              if [[ "${DEDUP_BASE}" == "0" ]] || ! docker image inspect "${from_image}" >/dev/null 2>&1; then
                # shellcheck disable=SC2086
                docker build ${DOCKER_BUILD_OPTS} \
                  -f "${base_df}" \
                  -t "${from_image}" \
                  "${DOCKERFILES_ROOT}/base_dockerfile/${id}"
              fi
            ) 9>"${lockf}"
          else
            if [[ "${DEDUP_BASE}" == "0" ]] || ! docker image inspect "${from_image}" >/dev/null 2>&1; then
              # shellcheck disable=SC2086
              docker build ${DOCKER_BUILD_OPTS} \
                -f "${base_df}" \
                -t "${from_image}" \
                "${DOCKERFILES_ROOT}/base_dockerfile/${id}"
            fi
          fi
        fi

        echo "Build instance -> ${itag}"
        # shellcheck disable=SC2086
        docker build ${DOCKER_BUILD_OPTS} \
          -f "${inst_df}" \
          -t "${itag}" \
          "${DOCKERFILES_ROOT}/instance_dockerfile/${id}"
      fi
    fi

    if [[ "${BUILD_SIF}" == "1" ]]; then
      if [[ -z "${SINGULARITY_BIN}" ]]; then
        echo "ERROR: BUILD_SIF=1 but no apptainer/singularity on PATH" >&2
        exit 1
      fi
      local sif="${OUTPUT_DIR}/${id}.sif"
      if [[ "${SKIP_EXISTING_SIF}" == "1" && -f "${sif}" ]]; then
        echo "Skip existing SIF: ${sif}"
      else
        echo "Build SIF -> ${sif}"
        # docker-daemon: requires access to local Docker; may need fakeroot on some sites.
        "${SINGULARITY_BIN}" build --force "${sif}" "docker-daemon://${itag}"
      fi
    fi
    echo "OK ${id}"
  } 2>&1 | tee -a "${log}"
}

export -f build_one parse_from_image instance_docker_tag
export REPO_ROOT DOCKERFILES_ROOT OUTPUT_DIR LOG_DIR BUILD_SIF SIF_ONLY
export SKIP_EXISTING_SIF SKIP_EXISTING_IMAGE DEDUP_BASE PARALLEL DOCKER_BUILD_OPTS
export SINGULARITY_BIN

mapfile -t IDS < <(
  find "${DOCKERFILES_ROOT}/instance_dockerfile" -mindepth 1 -maxdepth 1 -type d |
    sed 's|.*/||' | sort
)

filtered=()
for id in "${IDS[@]}"; do
  case "${id}" in
    ${INSTANCE_FILTER}) filtered+=("${id}") ;;
  esac
done

echo "Instances to process: ${#filtered[@]} (filter: ${INSTANCE_FILTER})"
echo "DOCKERFILES_ROOT=${DOCKERFILES_ROOT}  OUTPUT_DIR=${OUTPUT_DIR}  PARALLEL=${PARALLEL}"

if [[ "${#filtered[@]}" -eq 0 ]]; then
  echo "Nothing to do."
  exit 0
fi

if [[ "${PARALLEL}" -le 1 ]]; then
  failed=0
  for id in "${filtered[@]}"; do
    if ! build_one "${id}"; then
      echo "FAILED ${id} (see ${LOG_DIR}/${id}.log)" >&2
      failed=1
    fi
  done
  exit "${failed}"
fi

if xargs --help 2>&1 | grep -qF -- '-r'; then
  XARGS_NO_RUN=(-r)
else
  XARGS_NO_RUN=()
fi

printf '%s\n' "${filtered[@]}" | xargs "${XARGS_NO_RUN[@]}" -P "${PARALLEL}" -I'{}' \
  bash -c 'cd "$1" && build_one "$2"' _ "${REPO_ROOT}" '{}'
