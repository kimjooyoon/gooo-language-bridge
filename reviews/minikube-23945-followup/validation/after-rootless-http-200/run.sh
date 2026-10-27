sudo apt-get remove moby-engine-*
(set -o pipefail; curl --fail --location https://get.docker.com | sudo sh)
dockerd-rootless-setuptool.sh install -f
docker context use rootless

printf continued > continued
