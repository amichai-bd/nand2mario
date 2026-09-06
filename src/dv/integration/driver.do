# Byte-only live bridge. The builder owns the Python peer process.
proc observe {name} { return [examine -radix unsigned sim:/tb_integration/$name] }
proc deposit {name value} { force -deposit sim:/tb_integration/$name 10#$value }
proc advance {} { run 100 us }
proc progress {phase} {
    global ordinal started
    puts "SMOKE_DRIVER phase=$phase ordinal=$ordinal wall_ms=[expr {[clock milliseconds]-$started}] sim_ns=[observe simulation_ns] tx_count=[observe tx_count] tx_busy=[observe tx_busy] rx_count=[observe rx_count] rx_done=[observe rx_done]"
}
proc bounded_wait {expression} {
    set deadline [expr {[clock milliseconds] + 30000}]
    while {![uplevel 1 [list expr $expression]]} {
        if {[clock milliseconds] >= $deadline} { error "SMOKE_DRIVER_RESPONSE_TIMEOUT" }
        advance
    }
}
set ordinal 0
set started [clock milliseconds]
set channel [socket 127.0.0.1 $smoke_peer_port]
fconfigure $channel -blocking 0 -buffering line -translation lf -encoding ascii
run 1 us
set deadline [expr {[clock milliseconds] + 30000}]
while {1} {
    set count [gets $channel line]
    if {$count < 0} {
        if {[eof $channel]} { error "SMOKE_DRIVER_PEER_EOF" }
        if {[clock milliseconds] >= $deadline} { error "SMOKE_DRIVER_PEER_TIMEOUT" }
        after 1
        continue
    }
    set deadline [expr {[clock milliseconds] + 30000}]
    if {[string length $line] > 1024} { error "SMOKE_DRIVER_LINE_SIZE" }
    if {[regexp {^TX ([0-9a-f]+)$} $line whole hex]} {
        incr ordinal
        progress received
        set length [expr {[string length $hex] / 2}]
        if {[string length $hex] % 2 || $length < 1 || $length > 272 || [observe tx_busy]} {
            error "SMOKE_DRIVER_TX_SIZE"
        }
        deposit rx_count 0
        deposit rx_done 0
        for {set i 0} {$i < $length} {incr i} {
            scan [string range $hex [expr {2*$i}] [expr {2*$i+1}]] %x byte
            deposit "tx_bytes($i)" $byte
        }
        deposit tx_count $length
        progress prepared
        deposit tx_go 1
        bounded_wait {[observe rx_done] && ![observe tx_busy]}
        progress response
        set reply ""
        set length [observe rx_count]
        if {$length < 1 || $length > 272} { error "SMOKE_DRIVER_RX_SIZE" }
        for {set i 0} {$i < $length} {incr i} {
            append reply [format %02x [observe "rx_bytes($i)"]]
        }
        progress extracted
        puts $channel "RX [observe simulation_ns] $reply"
        flush $channel
    } elseif {[regexp {^WAIT ([0-9]+)$} $line whole wanted]} {
        if {$wanted != 136280} { error "SMOKE_DRIVER_WAIT_RANGE" }
        bounded_wait {[observe dot_count] >= $wanted}
        puts $channel "WAITED [observe simulation_ns]"
        flush $channel
    } elseif {$line eq "DONE"} {
        close $channel
        deposit finish_request 1
        run 1 us
        error "SMOKE_DRIVER_MISSING_FINISH"
    } else {
        error "SMOKE_DRIVER_MESSAGE"
    }
}
