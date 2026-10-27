sudo apt-get remove moby-engine-*
curl https://get.docker.com | sudo sh
dockerd-rootless-setuptool.sh install -f
docker context use rootless

printf continued > continued
