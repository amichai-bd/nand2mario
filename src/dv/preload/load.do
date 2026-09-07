# Acknowledge generated inputs; all fixture stimulus and checking are in SV.
set channel [socket 127.0.0.1 $smoke_peer_port]
close $channel
run -all
