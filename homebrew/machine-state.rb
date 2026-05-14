class MachineState < Formula
  desc "Local-first machine awareness daemon for macOS"
  homepage "https://github.com/sashreek-das/machine-state"
  version "0.1.0"
  license "MIT"

  # Apple Silicon only for now; Intel support coming in a future release.
  # SHA256 is printed by the GitHub Actions release job — update after each release.
  url "https://github.com/sashreek-das/machine-state/releases/download/v#{version}/machine-state-arm64.tar.gz"
  sha256 "f3aa95172172ad8739d7ddf05d8fa2494b6fa9ecc560ebdac8adf9fdde6e79f5"

  def install
    bin.install "machine-state-arm64" => "machine-state"
  end

  def post_install
    # Runtime data directory
    (Dir.home + "/.machine-state").tap { |d| FileUtils.mkdir_p(d) }

    # LaunchAgent: starts the snapshot scheduler automatically on every login.
    launch_agents = Dir.home + "/Library/LaunchAgents"
    FileUtils.mkdir_p(launch_agents)
    plist = launch_agents + "/com.machine-state.scheduler.plist"

    File.write(plist, <<~XML)
      <?xml version="1.0" encoding="UTF-8"?>
      <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
        "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
      <plist version="1.0">
      <dict>
        <key>Label</key>
        <string>com.machine-state.scheduler</string>
        <key>ProgramArguments</key>
        <array>
          <string>#{bin}/machine-state</string>
          <string>scheduler</string>
          <string>start</string>
        </array>
        <key>RunAtLoad</key>
        <true/>
        <key>KeepAlive</key>
        <false/>
        <key>StandardErrorPath</key>
        <string>#{Dir.home}/.machine-state/scheduler.log</string>
      </dict>
      </plist>
    XML

    # Reload: unload first to handle upgrades cleanly, then load.
    system "launchctl", "unload", plist.to_s, err: :close
    system "launchctl", "load", plist.to_s
  end

  test do
    assert_match "usage: machine-state", shell_output("#{bin}/machine-state --help 2>&1")
  end
end
