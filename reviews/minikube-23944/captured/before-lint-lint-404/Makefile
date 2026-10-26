GOLINT_VERSION=v9.9.9
all: out/linters/golangci-lint-$(GOLINT_VERSION)
out/linters/golangci-lint-$(GOLINT_VERSION):
	mkdir -p out/linters
	version="$(GOLINT_VERSION)"; \
	version=$${version#v}; \
	os=$$(go env GOOS); \
	arch=$$(go env GOARCH); \
	name="golangci-lint-$${version}-$${os}-$${arch}"; \
	checksums="out/linters/golangci-lint-$${version}-checksums.txt"; \
	if [ "$${os}" = "windows" ]; then \
		ext="zip"; \
		suffix=".exe"; \
	else \
		ext="tar.gz"; \
		suffix=""; \
	fi; \
	archive="out/linters/$${name}.$${ext}"; \
	curl -sfL -o "$${checksums}" "https://github.com/golangci/golangci-lint/releases/download/$(GOLINT_VERSION)/golangci-lint-$${version}-checksums.txt"; \
	curl -sfL -o "$${archive}" "https://github.com/golangci/golangci-lint/releases/download/$(GOLINT_VERSION)/$${name}.$${ext}"; \
	want=$$(awk -v file="$${name}.$${ext}" '$$2 == file { print $$1; exit }' "$${checksums}"); \
	got=$$(openssl sha256 "$${archive}" | awk '{print $$2}'); \
	test -n "$${want}" && test "$${want}" = "$${got}"; \
	tmpdir=$$(mktemp -d); \
	if [ "$${os}" = "windows" ]; then \
		unzip -q "$${archive}" -d "$${tmpdir}"; \
	else \
		tar -xzf "$${archive}" -C "$${tmpdir}"; \
		chmod +x "$${tmpdir}/$${name}/golangci-lint"; \
	fi; \
	mv "$${tmpdir}/$${name}/golangci-lint$${suffix}" "$@"; \
	rm -rf "$${tmpdir}" "$${archive}" "$${checksums}"
