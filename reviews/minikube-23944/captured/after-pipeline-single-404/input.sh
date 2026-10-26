set -e -o pipefail
install_k3d() {
	curl --fail --silent --show-error https://raw.githubusercontent.com/rancher/k3d/main/install.sh | bash
}
install_k3d
printf continued > continued
