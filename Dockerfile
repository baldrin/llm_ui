FROM python:3.9-slim 

ENV TZ=America/Chicago
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    vim \
    screen \
    build-essential \
    cmake \
    pkg-config \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    wget \
    curl \
    dnsutils \
    iputils-ping \
    sudo \
    git \
    htop \
    ncdu \
    tmux \
    jq \
    zip \
    unzip \
    less \
    man-db \
    openssh-client \
    locales \
    && rm -rf /var/lib/apt/lists/*

# Configure locale settings
RUN localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8
ENV LANG=en_US.utf8

# Create devuser and add to sudo group
RUN useradd -ms /bin/bash devuser && \
    adduser devuser sudo && \
    echo "devuser ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/devuser && \
    chmod 0440 /etc/sudoers.d/devuser

ENV PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org pypi.python.org"

# Copy requirements file and install packages
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org -r /tmp/requirements.txt

# Install additional development tools
RUN pip install --no-cache-dir \
    pytest \
    flake8 \
    black \
    isort 

# Set up git configuration for devuser
WORKDIR /home/devuser

USER devuser
RUN git config --global core.editor "vim" && \
    git config --global color.ui auto

# Set the entrypoint
CMD ["/bin/bash"]