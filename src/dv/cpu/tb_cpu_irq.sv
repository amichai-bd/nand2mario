`timescale 1ns/1ps
`default_nettype none

module tb_cpu_irq;
    logic clk_sys;
    logic reset_sys;
    logic core_reset;
    logic gb_tick;
    logic [7:0] profile_id;
    logic [31:0] epoch;
    logic [63:0] dot_before;
    logic [7:0] ie;
    logic [4:0] iflags;
    logic [7:0] buttons;
    logic [7:0] read_data;
    logic response_valid;
    logic [1:0] stop_action;
    logic stop_padding;
    logic wake_request;
    logic request_valid;
    logic [15:0] address;
    logic [7:0] write_data;
    logic write_enable;
    n2m_cpu_pkg::access_kind_t access_kind;
    logic bus_commit;
    logic [4:0] irq_ack;
    logic halted;
    logic stopped;
    logic locked;
    logic initialized;
    logic fault;
    logic ime_observe;
    logic ime_delay_observe;
    logic stop_execute;
    logic retirement_valid;
    n2m_interfaces_pkg::retirement_t retirement;

    logic [7:0] memory [65536];
    logic [383:0] expected;
    logic [15:0] start_sp;
    logic [15:0] return_pc;
    logic [15:0] vector_pc;
    logic [15:0] expected_address;
    logic [7:0] request_bits;
    logic [7:0] selected_bit;
    logic [7:0] expected_byte;
    logic [2:0] expected_kind;
    logic expected_write;
    integer scenario;
    integer item;
    integer cycle;
    integer trace;
    integer event_index;
    integer recognition_dot;
    integer arrival_dot;
    integer mcycle;
    integer elapsed;
    integer expected_events;
    integer event_dot;
    bit same_edge;
    bit observed_entry;
    bit pause_done;
    integer pause_cycle;
    bit corrupt;

    n2m_cpu_control dut (.*);
    assign read_data = address == 16'hffff ? ie :
        (address == 16'hff0f ? {3'b111, iflags} : memory[address]);

    // The test owns storage. These cases avoid ambiguous simultaneous external
    // set/CPU-write/ack collisions; IRQ selection still observes the old snapshot.
    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) dot_before <= 0;
        else if (gb_tick) dot_before <= dot_before + 64'd1;
        if (bus_commit && write_enable) begin
            memory[address] <= write_data;
            if (address == 16'hffff) ie <= write_data;
            if (address == 16'hff0f) iflags <= write_data[4:0] & ~irq_ack;
            else if (|irq_ack) iflags <= iflags & ~irq_ack;
        end
        if (same_edge && gb_tick && dot_before == 26) iflags <= request_bits[4:0];
    end

    task automatic check_bus;
        if (bus_commit && (!gb_tick || dot_before[1:0] != 3))
            $fatal(1, "CPU_IRQ_EARLY_COMMIT case=%0d dot=%0d", scenario, dot_before+1);
        if (gb_tick && dot_before[1:0] == 3) begin
            mcycle = int'((dot_before + 1) / 4);
            expected_kind = 1;
            expected_write = 0;
            expected_address = 16'(16'h0100 + mcycle - 1);
            expected_byte = memory[expected_address];
            if (mcycle == 2 || mcycle == 3) expected_kind = 2;
            if (mcycle > recognition_dot / 4) begin
                elapsed = mcycle - recognition_dot / 4;
                expected_kind = 0;
                if (elapsed == 3 || elapsed == 4) begin
                    expected_kind = 4;
                    expected_write = 1;
                    expected_address = start_sp - 16'(elapsed - 2);
                    expected_byte = elapsed == 3 ? return_pc[15:8] : return_pc[7:0];
                end else if (elapsed == 5) begin
                    expected_kind = 1;
                    expected_address = vector_pc;
                    expected_byte = memory[vector_pc];
                end
            end
            $fdisplay(trace, "bus,%0d,%0d,%0d,%04h,%0d,%02h", scenario, dot_before+1,
                access_kind,address,write_enable,write_enable ? write_data : read_data);
            if (bus_commit !== (expected_kind != 0) ||
                (expected_kind != 0 && (access_kind !== expected_kind ||
                address !== expected_address || write_enable !== expected_write ||
                (write_enable ? write_data : read_data) !== expected_byte)))
                $fatal(1, "CPU_IRQ_BUS case=%0d dot=%0d expected=%0d/%04h/%02h actual=%0d/%04h/%02h",
                    scenario,dot_before+1,expected_kind,expected_address,expected_byte,
                    access_kind,address,write_enable ? write_data : read_data);
            if (irq_ack !== ((dot_before + 1 == recognition_dot + 16) ? selected_bit[4:0] : 5'b0))
                $fatal(1, "CPU_IRQ_ACK case=%0d dot=%0d expected=%02h actual=%02h",
                    scenario,dot_before+1,selected_bit,irq_ack);
        end
    endtask

    task automatic check_event;
        if (retirement_valid) begin
            expected = '0;
            expected[0 +: 8] = 1;
            expected[16 +: 32] = 32'(scenario + 1);
            expected[48 +: 64] = 64'(event_index);
            expected[304 +: 16] = start_sp;
            expected[360 +: 8] = ie;
            expected[368 +: 8] = {3'b0,iflags};
            if (event_index == expected_events - 1) begin
                expected[8 +: 8] = 1;
                expected[112 +: 64] = 64'(recognition_dot + 20);
                expected[176 +: 16] = return_pc;
                expected[192 +: 16] = vector_pc;
                expected[304 +: 16] = start_sp - 16'd2;
                observed_entry = 1;
            end else begin
                event_dot = event_index == 0 ? 16 : 16 + 4*event_index;
                expected[112 +: 64] = 64'(event_dot);
                if (event_index == 0) begin
                    expected[176 +: 16] = 16'h0100;
                    expected[192 +: 16] = 16'h0103;
                    expected[208 +: 24] = {start_sp,8'h31};
                    expected[232 +: 8] = 3;
                end else begin
                    expected[176 +: 16] = 16'(16'h0102 + event_index);
                    expected[192 +: 16] = 16'(16'h0103 + event_index);
                    expected[208 +: 24] = {16'b0,memory[16'h0102 + event_index]};
                    expected[232 +: 8] = 1;
                    if (event_index == 1) expected[328 +: 8] = 1;
                    else expected[320 +: 8] = 1;
                    if ((scenario == 3 || scenario == 4) && event_dot == recognition_dot)
                        expected[192 +: 16] = return_pc;
                end
            end
            $fdisplay(trace,"retire,%0d,%0d,%096h,%096h",scenario,event_index,expected,retirement);
            if (retirement !== expected)
                $fatal(1,"CPU_IRQ_EVENT case=%0d event=%0d expected=%096h actual=%096h",
                    scenario,event_index,expected,retirement);
            event_index = event_index + 1;
        end
    endtask

    task automatic edge_cycle(input bit tick);
        clk_sys = 0;
        gb_tick = tick;
        #4;
        if (!reset_sys && !core_reset) check_bus();
        #1 clk_sys = 1;
        #2;
        if (!reset_sys && !core_reset) check_event();
        #3 clk_sys = 0;
    endtask

    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0; profile_id=1;
        epoch=1; dot_before=0; ie=0; iflags=0; buttons=0;
        response_valid=1; stop_action=0; stop_padding=0; wake_request=0;
        same_edge=0; corrupt=$test$plusargs("corrupt");
        trace=$fopen("irq-trace.csv","w");
        if (!trace) $fatal(1,"CPU_IRQ_TRACE_OPEN");
        $dumpfile("waves/cpu-irq.vcd");
        $dumpvars(0,tb_cpu_irq);
        for (scenario=0; scenario<14; scenario=scenario+1) begin
            reset_sys=1;
            edge_cycle(0);
            for (item=0; item<65536; item=item+1) memory[item]=0;
            start_sp=16'hd000; request_bits=1; selected_bit=1; vector_pc=16'h40;
            recognition_dot=28; arrival_dot=26; return_pc=16'h106;
            same_edge=scenario==1;
            if (scenario==1 || scenario==2) begin
                recognition_dot=32; arrival_dot=27; return_pc=16'h107;
            end
            if (scenario==3) begin
                memory[16'h104]=8'h76;
                recognition_dot=24; arrival_dot=22; return_pc=16'h104;
            end
            if (scenario==4) begin memory[16'h105]=8'h76; return_pc=16'h105; end
            if (scenario==5) begin
                start_sp=0; request_bits=4; selected_bit=0; vector_pc=0;
            end
            if (scenario==6) start_sp=16'hff11;
            if (scenario==7) start_sp=1;
            if (scenario>=8 && scenario<=11) begin
                request_bits=8'(1 << (scenario-7)); selected_bit=request_bits;
                vector_pc=16'(16'h40 + 8*(scenario-7));
            end
            if (scenario==13) request_bits=31;
            memory[16'h100]=8'h31; memory[16'h101]=start_sp[7:0];
            memory[16'h102]=start_sp[15:8]; memory[16'h103]=8'hfb;
            ie=request_bits; iflags=0; epoch=32'(scenario+1);
            observed_entry=0; event_index=0; pause_done=0;
            expected_events=(recognition_dot-16)/4+2;
            reset_sys=0; core_reset=1; edge_cycle(0); core_reset=0;
            for (cycle=0; cycle<(recognition_dot+20)*3+2; cycle=cycle+1) begin
                if (!same_edge && dot_before==64'(arrival_dot)) iflags=request_bits[4:0];
                if (scenario==12 && dot_before==27 && !pause_done) begin
                    iflags=0;
                    for (pause_cycle=0; pause_cycle<20; pause_cycle=pause_cycle+1)
                        edge_cycle(0);
                    pause_done=1;
                end
                if (scenario==12 && dot_before==28) iflags=request_bits[4:0];
                if (corrupt && scenario==0 && dot_before==27)
                    force dut.control.irq_snapshot=5'b0;
                edge_cycle(cycle%3==0);
            end
            if (!observed_entry || event_index!=expected_events || fault || locked)
                $fatal(1,"CPU_IRQ_FINAL case=%0d events=%0d expected=%0d",scenario,event_index,expected_events);
        end
        $fclose(trace);
        $display("PASS CPU IRQ cases=14 T3 snapshot priorities stack HALT pause");
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1,"CPU_IRQ_TIMEOUT");
    end
endmodule
