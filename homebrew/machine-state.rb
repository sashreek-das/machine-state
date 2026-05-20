class MachineState < Formula
  desc "Local-first machine awareness daemon for macOS"
  homepage "https://github.com/sashreek-das/machine-state"
  version "0.1.2"
  license "MIT"

  # Apple Silicon only for now; Intel support coming in a future release.
  # SHA256 is printed by the GitHub Actions release job — update after each release.
  url "https://github.com/sashreek-das/machine-state/releases/download/v#{version}/machine-state-arm64.tar.gz"
  sha256 "2330b145158896d00706adff537ca977d4311c71f67b8311189cc1a9d2a4703e"

  def install
    bin.install "machine-state-arm64" => "machine-state"
  end

  def post_install
    # Runtime data directory
    (Dir.home + "/.machine-state").tap { |d| FileUtils.mkdir_p(d) }

    # v0.1.1 and earlier used a different LaunchAgent label. Unload and remove
    # the old plist so the new one takes over cleanly on upgrade.
    old_plist = Dir.home + "/Library/LaunchAgents/com.machine-state.scheduler.plist"
    if File.exist?(old_plist)
      system "launchctl", "unload", old_plist.to_s, err: :close
      FileUtils.rm_f(old_plist)
    end

    # Delegate LaunchAgent setup to the binary itself.
    # This writes ~/Library/LaunchAgents/com.machinestate.scheduler.plist,
    # sets KeepAlive: true (auto-restart on crash), and loads it via launchctl.
    system "#{bin}/machine-state", "scheduler", "install"
  end

  test do
    assert_match "usage: machine-state", shell_output("#{bin}/machine-state --help 2>&1")
  end
end
