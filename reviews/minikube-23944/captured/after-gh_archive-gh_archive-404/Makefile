all:
	@if ! command -v gh >/dev/null 2>&1; then \
		( \
			set -e; \
			echo "Determining latest gh version..."; \
			GH_URL=$$(curl --fail --location --silent --show-error --output /dev/null --write-out '%{url_effective}' https://github.com/cli/cli/releases/latest) || exit; \
			GH_TAG=$${GH_URL##*/}; \
			GH_TAG=$${GH_TAG#v}; \
			echo "Installing gh version $${GH_TAG}..."; \
			curl --fail --silent --show-error --location "https://github.com/cli/cli/releases/download/v$${GH_TAG}/gh_$${GH_TAG}_linux_amd64.tar.gz" --output /tmp/gh.tar.gz || exit; \
			tar -xf /tmp/gh.tar.gz -C /tmp; \
			mv /tmp/gh_$${GH_TAG}_linux_amd64/bin/gh /usr/local/bin/gh; \
			rm -rf /tmp/gh.tar.gz "/tmp/gh_$${GH_TAG}_linux_amd64"; \
		); \
	fi
