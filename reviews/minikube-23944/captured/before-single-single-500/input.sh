set -e
set -x
CRICTL_VERSION=v1.99.0
curl -L https://github.com/kubernetes-sigs/cri-tools/releases/download/$CRICTL_VERSION/crictl-${CRICTL_VERSION}-linux-amd64.tar.gz --output crictl-${CRICTL_VERSION}-linux-amd64.tar.gz
printf continued > continued
