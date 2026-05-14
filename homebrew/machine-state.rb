class MachineState < Formula
  desc "Local-first machine awareness daemon for macOS"
  homepage "https://github.com/sashreek-das/machine-state"
  version "0.1.0"
  license "MIT"

  # Apple Silicon only for now; Intel support coming in a future release.
  # SHA256 is printed by the GitHub Actions release job — update after each release.
  url "https://github.com/sashreek-das/machine-state/releases/download/v#{version}/machine-state-arm64.tar.gz"
  sha256 "294747e049a867f88cce3124d16103f04305bd149f0705919cad5d535f968e3c"

  def install
    bin.install "machine-state-arm64" => "machine-state"
  end

  def post_install
    (Dir.home + "/.machine-state").tap { |d| FileUtils.mkdir_p(d) }
  end

  test do
    assert_match "usage: machine-state", shell_output("#{bin}/machine-state --help 2>&1")
  end
end
