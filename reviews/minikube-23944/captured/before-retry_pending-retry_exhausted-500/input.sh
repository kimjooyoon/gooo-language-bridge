set -e
function retry_github_status() {
  local commit=$1
  local context=$2
  local state=$3
  local token=$4
  local target=$5

   # Retry in case we hit our GitHub API quota or fail other ways.
  local attempt=0
  local timeout=2
  local code=-1

  while [[ "${attempt}" -lt 8 ]]; do
    local out=$(mktemp)
    code=$(curl -o "${out}" -s --write-out "%{http_code}" -L  -u minikube-bot:$token \
      "https://api.github.com/repos/kubernetes/minikube/statuses/${commit}" \
      -H "Content-Type: application/json" \
      -X POST \
      -d "{\"state\": \"${state}\", \"description\": \"Jenkins\", \"target_url\": \"${target}\", \"context\": \"${context}\"}" || echo 999)

    # 2xx HTTP codes
    if [[ "${code}" =~ ^2 ]]; then
      break
    fi

    cat "${out}" && rm -f "${out}"
    echo "HTTP code ${code}! Retrying in ${timeout} .."
    sleep "${timeout}"
    attempt=$(( attempt + 1 ))
    timeout=$(( timeout * 5 ))
  done
}
retry_github_status deadbeef fixture pending fixture-token https://example.invalid fixture-description
printf continued > continued
