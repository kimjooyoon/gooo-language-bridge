all:
	@if ! command -v gh >/dev/null 2>&1; then \
		( \
			set -e; \
			echo "Determining latest gh version..."; \
			GH_TAG=$$(basename $$(curl -Ls -o /dev/null -w '%{url_effective}' https://github.com/cli/cli/releases/latest) | sed 's/^v//'); \
			echo "Installing gh version $${GH_TAG}..."; \
			curl -sSL "https://github.com/cli/cli/releases/download/v$${GH_TAG}/gh_$${GH_TAG}_linux_amd64.tar.gz" -o /tmp/gh.tar.gz; \
			tar -xf /tmp/gh.tar.gz -C /tmp; \
			mv /tmp/gh_$${GH_TAG}_linux_amd64/bin/gh /usr/local/bin/gh; \
			rm -rf /tmp/gh.tar.gz "/tmp/gh_$${GH_TAG}_linux_amd64"; \
		) || echo "WARNING: Failed to install gh dynamically, continuing using fallback..."; \
	fi
