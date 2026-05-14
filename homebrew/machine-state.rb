class MachineState < Formula
  desc "Local-first machine awareness daemon for macOS"
  homepage "https://github.com/sashreek/machine-state"
  version "0.1.0"
  license "MIT"

  # Pre-built binaries — no Python required on the target machine.
  # SHA256 values are printed by the GitHub Actions release job.
  # Update them here after each release.
  on_arm do
    url "https://github.com/sashreek/machine-state/releases/download/v#{version}/machine-state-arm64.tar.gz"
    sha256 "REPLACE_WITH_ARM64_SHA256"
  end

  on_intel do
    url "https://github.com/sashreek/machine-state/releases/download/v#{version}/machine-state-x86_64.tar.gz"
    sha256 "REPLACE_WITH_X86_64_SHA256"
  end

  def install
    arch = Hardware::CPU.arm? ? "arm64" : "x86_64"
    bin.install "machine-state-#{arch}" => "machine-state"
  end

  def post_install
    # Ensure the data directory exists on first install
    (var/"machine-state").mkpath
  end

  test do
    assert_match "machine-state", shell_output("#{bin}/machine-state --help")
  end
end
