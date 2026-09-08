#!/usr/bin/env bash
# Install the NVIDIA CUDA libraries Utterleaf needs for GPU transcription.
# Handles distro package managers for you; run this on the machine that
# runs the Utterleaf binary. Check with:  utterleaf --doctor
set -euo pipefail

if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "No NVIDIA driver detected (nvidia-smi not found). Install the driver first:"
    echo "  On Debian/Ubuntu:  sudo apt install nvidia-driver-565"
    echo "  On Arch:           sudo pacman -S nvidia"
    echo "  On Fedora:         sudo dnf install akmod-nvidia"
    exit 1
fi

# Identify the distro family.
if [[ -r /etc/os-release ]]; then
    id="$(. /etc/os-release && echo "${ID_LIKE:-$ID}")"
else
    id=""
fi
case "$id" in
    *arch*|*manjaro*)
        echo "Installing into Arch:  pacman -S --needed cuda cudnn"
        sudo pacman -S --needed cuda cudnn
        ;;
    *debian*|*ubuntu*)
        echo "Installing into Debian/Ubuntu:  nvidia-cuda-toolkit + cuDNN"
        sudo apt-get update
        # cuDNN release-matches the toolkit version; the toolkit keeps deploy simple.
        sudo apt-get install -y nvidia-cuda-toolkit
        if apt-cache search libcudnn | grep -q .; then
            echo "  cuDNN split package available; installing the meta package:"
            sudo apt-get install -y libcudnn8-cuda-12 || \
            sudo apt-get install -y libcudnn9-cuda-12 || true
        else
            echo "  cuDNN is not in your repositories. Install it manually:"
            echo "    https://developer.nvidia.com/cudnn-downloads"
        fi
        ;;
    *fedora*|*rhel*|*centos*)
        echo "Installing into Fedora/RHEL:  cuda-toolkit via NVIDIA repo"
        echo "  Using NVIDIA's RPM repo (auto-detects your major version):"
        rev_id="$(. /etc/os-release && echo "${VERSION_ID%%.*}")"
        /bin/bash /dev/stdin <<EOF
sudo dnf config-manager addrepo --from-repofile="https://developer.download.nvidia.com/compute/cuda/repos/fedora${rev_id}/x86_64/cuda-fedora${rev_id}.repo" 2>/dev/null || \
sudo dnf config-manager addrepo --from-repofile="https://developer.download.nvidia.com/compute/cuda/repos/rhel${rev_id}/x86_64/cuda-rhel${rev_id}.repo"
sudo dnf -y install cuda-toolkit
EOF
        ;;
    *)
        echo "Unrecognized distro (id='$id'). Install CUDA for your distribution:"
        echo "    https://developer.nvidia.com/cuda-downloads"
        echo "Then install cuDNN:  https://developer.nvidia.com/cudnn-downloads"
        ;;
esac

echo
echo "Done. Restart Utterleaf; '--doctor' should list the GPU as ready."