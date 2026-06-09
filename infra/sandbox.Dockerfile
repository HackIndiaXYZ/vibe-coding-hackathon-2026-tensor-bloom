# Cosign sandbox image — the environment agents run inside (ARCHITECTURE §6.2).
# One ephemeral container per agent task; destroyed when the run ends.
FROM debian:bookworm-slim

# Core toolchain agents need to clone, build, test, and lint repos.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        ca-certificates \
        curl \
        bash \
        make \
        jq \
        ripgrep \
        python3 \
        python3-venv \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Node LTS (for jest / npm-based repos) via NodeSource.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Non-root user to run all agent commands as.
RUN useradd --create-home --shell /bin/bash agent \
    && mkdir -p /workspace \
    && chown agent:agent /workspace

# GIT_ASKPASS helper: reads the token from an env var so it is never written to
# disk. The DockerDriver sets GIT_ASKPASS=/usr/local/bin/git-askpass and passes
# GITHUB_TOKEN in the exec env; git invokes this for credential prompts.
RUN printf '#!/bin/bash\necho "$GITHUB_TOKEN"\n' > /usr/local/bin/git-askpass \
    && chmod 0755 /usr/local/bin/git-askpass

USER agent
WORKDIR /workspace
ENV GIT_ASKPASS=/usr/local/bin/git-askpass \
    GIT_TERMINAL_PROMPT=0

# Containers are driven via `docker exec`; keep one alive so the driver can exec
# into it for the lifetime of a task.
CMD ["sleep", "infinity"]
