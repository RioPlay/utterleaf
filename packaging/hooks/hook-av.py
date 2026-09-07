# Intentionally empty. This overrides the contrib hook-av.py, which would
# otherwise collect_dynamic_libs("av") from site-packages and bundle PyAV's
# GPL-licensed FFmpeg DLLs. The `av` module in this build is packaging/stubs/av
# (see packaging/utterleaf.spec pathex) — never the real PyAV.
