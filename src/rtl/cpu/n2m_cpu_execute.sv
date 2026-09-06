`default_nettype none

// One execution M-cycle. The front end owns T phases, fetch overlap, reset,
// sleep and interrupt dispatch. This block never changes state itself.
module n2m_cpu_execute (
    input wire n2m_cpu_pkg::cpu_registers_t registers,
    input wire logic [7:0] opcode,
    input wire logic cb_bank,
    input wire logic [2:0] step,
    input wire logic [15:0] pc,
    input wire logic [15:0] temporary,
    input wire logic [7:0] data_in,
    output n2m_cpu_pkg::cpu_registers_t registers_next,
    output logic [15:0] pc_next,
    output logic [15:0] temporary_next,
    output logic [15:0] address,
    output logic [7:0] write_data,
    output logic write_enable,
    output n2m_cpu_pkg::access_kind_t access_kind,
    output logic finish,
    output logic prefix,
    output logic halt_request,
    output logic stop_request,
    output logic illegal,
    output logic enable_interrupts,
    output logic disable_interrupts,
    output logic return_interrupt
);
    import n2m_cpu_pkg::*;

    logic [4:0] alu_operation;
    logic [7:0] alu_lhs;
    logic [7:0] alu_rhs;
    logic [7:0] alu_value;
    logic [7:0] alu_flags;
    logic [15:0] pair_value;
    logic [16:0] wide_pair;
    logic [12:0] low_pair;
    logic [15:0] signed_result;
    logic [8:0] signed_low;
    logic [4:0] signed_nibble;
    logic taken;
    logic [2:0] return_step;

    n2m_cpu_alu alu (
        .operation(alu_operation), .lhs(alu_lhs), .rhs(alu_rhs),
        .flags_in(registers.f), .bit_index(opcode[5:3]),
        .value(alu_value), .flags_out(alu_flags)
    );

    always_comb begin
        alu_operation = ALU_ADD;
        alu_lhs = registers.a;
        alu_rhs = read_byte(registers, opcode[2:0]);
        if (opcode[2:0] == 6) alu_rhs = temporary[7:0];
        if (opcode[7:6] == 2'b10 || opcode[7:6] == 2'b11)
            alu_operation = {2'b0, opcode[5:3]};
        if (opcode[7:6] == 2'b11) alu_rhs = temporary[7:0];
        if (opcode[7:6] == 0 && (opcode[2:0] == 4 || opcode[2:0] == 5)) begin
            alu_operation = opcode[0] ? ALU_DEC : ALU_INC;
            alu_lhs = opcode[5:3] == 6 ? temporary[7:0] : read_byte(registers, opcode[5:3]);
        end
        case (opcode)
            8'h07: alu_operation = ALU_RLCA;
            8'h0f: alu_operation = ALU_RRCA;
            8'h17: alu_operation = ALU_RLA;
            8'h1f: alu_operation = ALU_RRA;
            8'h27: alu_operation = ALU_DAA;
            8'h2f: alu_operation = ALU_CPL;
            8'h37: alu_operation = ALU_SCF;
            8'h3f: alu_operation = ALU_CCF;
            default: begin end
        endcase
        if (cb_bank) begin
            alu_lhs = opcode[2:0] == 6 ? temporary[7:0] : read_byte(registers, opcode[2:0]);
            case (opcode[7:6])
                0: alu_operation = ALU_RLC + {2'b0, opcode[5:3]};
                1: alu_operation = ALU_BIT;
                2: alu_operation = ALU_RES;
                default: alu_operation = ALU_SET;
            endcase
        end
    end

    always_comb begin
        registers_next = registers;
        pc_next = pc;
        temporary_next = temporary;
        address = pc;
        write_data = 0;
        write_enable = 0;
        access_kind = ACCESS_IDLE;
        finish = 0;
        prefix = 0;
        halt_request = 0;
        stop_request = 0;
        illegal = 0;
        enable_interrupts = 0;
        disable_interrupts = 0;
        return_interrupt = 0;
        pair_value = read_pair(registers, opcode[5:4], 0);
        wide_pair = {1'b0, registers.h, registers.l} + {1'b0, pair_value};
        low_pair = {1'b0, registers.h[3:0], registers.l} + {1'b0, pair_value[11:0]};
        signed_result = registers.sp + {{8{temporary[7]}}, temporary[7:0]};
        signed_low = {1'b0, registers.sp[7:0]} + {1'b0, temporary[7:0]};
        signed_nibble = {1'b0, registers.sp[3:0]} + {1'b0, temporary[3:0]};
        taken = condition_true(opcode[4:3], registers.f);
        return_step = step;

        if (cb_bank) begin
            if (opcode[2:0] == 6 && step == 0) begin
                access_kind = ACCESS_DATA;
                address = {registers.h, registers.l};
                temporary_next[7:0] = data_in;
            end else if (opcode[2:0] == 6 && opcode[7:6] != 1 && step == 1) begin
                access_kind = ACCESS_DATA;
                address = {registers.h, registers.l};
                write_enable = 1;
                write_data = alu_value;
                registers_next.f = alu_flags;
            end else begin
                finish = 1;
                if (opcode[2:0] != 6)
                    registers_next = write_byte(registers, opcode[2:0], alu_value);
                registers_next.f = alu_flags;
            end
        end else if (opcode >= 8'h40 && opcode <= 8'h7f) begin
            if (opcode == 8'h76) begin
                finish = 1;
                halt_request = 1;
            end else if (step == 0 && (opcode[2:0] == 6 || opcode[5:3] == 6)) begin
                access_kind = ACCESS_DATA;
                address = {registers.h, registers.l};
                if (opcode[5:3] == 6) begin
                    write_enable = 1;
                    write_data = read_byte(registers, opcode[2:0]);
                end else temporary_next[7:0] = data_in;
            end else begin
                finish = 1;
                if (opcode[5:3] != 6)
                    registers_next = write_byte(registers, opcode[5:3], opcode[2:0] == 6 ? temporary[7:0] : read_byte(registers, opcode[2:0]));
            end
        end else if (opcode >= 8'h80 && opcode <= 8'hbf) begin
            if (opcode[2:0] == 6 && step == 0) begin
                access_kind = ACCESS_DATA;
                address = {registers.h, registers.l};
                temporary_next[7:0] = data_in;
            end else begin
                finish = 1;
                registers_next.a = alu_value;
                registers_next.f = alu_flags;
            end
        end else if (opcode[7:6] == 0 && (opcode[2:0] == 4 || opcode[2:0] == 5)) begin
            if (opcode[5:3] == 6 && step == 0) begin
                access_kind = ACCESS_DATA;
                address = {registers.h, registers.l};
                temporary_next[7:0] = data_in;
            end else if (opcode[5:3] == 6 && step == 1) begin
                access_kind = ACCESS_DATA;
                address = {registers.h, registers.l};
                write_enable = 1;
                write_data = alu_value;
                registers_next.f = alu_flags;
            end else begin
                finish = 1;
                if (opcode[5:3] != 6) registers_next = write_byte(registers, opcode[5:3], alu_value);
                registers_next.f = alu_flags;
            end
        end else if (opcode[7:6] == 0 && opcode[2:0] == 6) begin
            if (step == 0) begin
                access_kind = ACCESS_OPERAND;
                pc_next = pc + 16'd1;
                temporary_next[7:0] = data_in;
            end else if (opcode[5:3] == 6 && step == 1) begin
                access_kind = ACCESS_DATA;
                address = {registers.h, registers.l};
                write_enable = 1;
                write_data = temporary[7:0];
            end else begin
                finish = 1;
                if (opcode[5:3] != 6) registers_next = write_byte(registers, opcode[5:3], temporary[7:0]);
            end
        end else if (opcode[7:6] == 0 && opcode[3:0] == 1) begin
            if (step < 2) begin
                access_kind = ACCESS_OPERAND;
                pc_next = pc + 16'd1;
                if (step == 0) temporary_next[7:0] = data_in;
                else temporary_next[15:8] = data_in;
            end else begin
                finish = 1;
                registers_next = write_pair(registers, opcode[5:4], 0, temporary);
            end
        end else if (opcode[7:6] == 0 && (opcode[3:0] == 3 || opcode[3:0] == 11)) begin
            if (step == 0)
                registers_next = write_pair(registers, opcode[5:4], 0, opcode[3] ? pair_value - 16'd1 : pair_value + 16'd1);
            else finish = 1;
        end else if (opcode[7:6] == 0 && opcode[3:0] == 9) begin
            if (step == 1) begin
                finish = 1;
                {registers_next.h, registers_next.l} = wide_pair[15:0];
                registers_next.f = {registers.f[7], 1'b0, low_pair[12], wide_pair[16], 4'b0};
            end
        end else if (opcode[7:6] == 0 && opcode[2:0] == 2) begin
            if (step == 0) begin
                access_kind = ACCESS_DATA;
                address = opcode[5] ? {registers.h, registers.l} : read_pair(registers, {1'b0, opcode[4]}, 0);
                write_enable = !opcode[3];
                write_data = registers.a;
                if (opcode[3]) temporary_next[7:0] = data_in;
                if (opcode[5]) {registers_next.h, registers_next.l} = opcode[4] ? address - 16'd1 : address + 16'd1;
            end else begin
                finish = 1;
                if (opcode[3]) registers_next.a = temporary[7:0];
            end
        end else if (opcode == 8'h18 || (opcode & 8'he7) == 8'h20) begin
            if (step == 0) begin
                access_kind = ACCESS_OPERAND;
                pc_next = pc + 16'd1;
                temporary_next[7:0] = data_in;
            end else if (step == 1 && (opcode == 8'h18 || taken))
                pc_next = pc + {{8{temporary[7]}}, temporary[7:0]};
            else finish = 1;
        end else if (opcode == 8'hc3 || (opcode & 8'he7) == 8'hc2 || opcode == 8'hcd || (opcode & 8'he7) == 8'hc4) begin
            if (step < 2) begin
                access_kind = ACCESS_OPERAND;
                pc_next = pc + 16'd1;
                if (step == 0) temporary_next[7:0] = data_in;
                else temporary_next[15:8] = data_in;
            end else if (step == 2 && !(opcode == 8'hc3 || opcode == 8'hcd || taken)) finish = 1;
            else if (opcode == 8'hc3 || opcode[2:0] == 2) begin
                if (step == 2) pc_next = temporary;
                else finish = 1;
            end else if (step == 2) registers_next.sp = registers.sp - 16'd1;
            else if (step == 3 || step == 4) begin
                access_kind = ACCESS_STACK;
                address = registers.sp;
                write_enable = 1;
                if (step == 3) begin
                    write_data = pc[15:8];
                    registers_next.sp = registers.sp - 16'd1;
                end else begin
                    write_data = pc[7:0];
                    pc_next = temporary;
                end
            end else finish = 1;
        end else if (opcode == 8'hc9 || opcode == 8'hd9 || (opcode & 8'he7) == 8'hc0) begin
            if ((opcode & 8'he7) == 8'hc0) begin
                return_step = step - 3'd1;
                if (!taken && step == 1) finish = 1;
            end
            if (!((opcode & 8'he7) == 8'hc0) || (taken && step != 0)) begin
                if (return_step < 2) begin
                    access_kind = ACCESS_STACK;
                    address = registers.sp;
                    registers_next.sp = registers.sp + 16'd1;
                    if (return_step == 0) temporary_next[7:0] = data_in;
                    else temporary_next[15:8] = data_in;
                end else if (return_step == 2) pc_next = temporary;
                else begin
                    finish = 1;
                    return_interrupt = opcode == 8'hd9;
                end
            end
        end else if ((opcode & 8'hcf) == 8'hc5 || (opcode & 8'hc7) == 8'hc7) begin
            pair_value = read_pair(registers, opcode[5:4], 1);
            if (step == 0) registers_next.sp = registers.sp - 16'd1;
            else if (step == 1 || step == 2) begin
                access_kind = ACCESS_STACK;
                address = registers.sp;
                write_enable = 1;
                if (step == 1) begin
                    write_data = opcode[1] ? pc[15:8] : pair_value[15:8];
                    registers_next.sp = registers.sp - 16'd1;
                end else begin
                    write_data = opcode[1] ? pc[7:0] : pair_value[7:0];
                    if (opcode[1]) pc_next = {10'b0, opcode[5:3], 3'b0};
                end
            end else finish = 1;
        end else if ((opcode & 8'hcf) == 8'hc1) begin
            if (step < 2) begin
                access_kind = ACCESS_STACK;
                address = registers.sp;
                registers_next.sp = registers.sp + 16'd1;
                if (step == 0) temporary_next[7:0] = data_in;
                else temporary_next[15:8] = data_in;
            end else begin
                finish = 1;
                registers_next = write_pair(registers, opcode[5:4], 1, temporary);
            end
        end else if ((opcode & 8'hc7) == 8'hc6) begin
            if (step == 0) begin
                access_kind = ACCESS_OPERAND;
                pc_next = pc + 16'd1;
                temporary_next[7:0] = data_in;
            end else begin
                finish = 1;
                registers_next.a = alu_value;
                registers_next.f = alu_flags;
            end
        end else case (opcode)
            8'h00: finish = 1;
            8'h07, 8'h0f, 8'h17, 8'h1f, 8'h27, 8'h2f, 8'h37, 8'h3f: begin
                finish = 1;
                registers_next.a = alu_value;
                registers_next.f = alu_flags;
            end
            8'h08, 8'hea, 8'hfa: begin
                if (step < 2) begin
                    access_kind = ACCESS_OPERAND;
                    pc_next = pc + 16'd1;
                    if (step == 0) temporary_next[7:0] = data_in;
                    else temporary_next[15:8] = data_in;
                end else if (step == 2 || (opcode == 8'h08 && step == 3)) begin
                    access_kind = ACCESS_DATA;
                    address = temporary;
                    if (step == 3) address = temporary + 16'd1;
                    write_enable = opcode != 8'hfa;
                    write_data = registers.a;
                    if (opcode == 8'h08) write_data = step == 2 ? registers.sp[7:0] : registers.sp[15:8];
                    if (opcode == 8'hfa) temporary_next[7:0] = data_in;
                end else begin
                    finish = 1;
                    if (opcode == 8'hfa) registers_next.a = temporary[7:0];
                end
            end
            8'he0, 8'hf0, 8'he2, 8'hf2: begin
                if (!opcode[1] && step == 0) begin
                    access_kind = ACCESS_OPERAND;
                    pc_next = pc + 16'd1;
                    temporary_next[7:0] = data_in;
                end else if ((!opcode[1] && step == 1) || (opcode[1] && step == 0)) begin
                    access_kind = ACCESS_DATA;
                    address = {8'hff, opcode[1] ? registers.c : temporary[7:0]};
                    write_enable = !opcode[4];
                    write_data = registers.a;
                    if (opcode[4]) temporary_next[7:0] = data_in;
                end else begin
                    finish = 1;
                    if (opcode[4]) registers_next.a = temporary[7:0];
                end
            end
            8'he8, 8'hf8: begin
                if (step == 0) begin
                    access_kind = ACCESS_OPERAND;
                    pc_next = pc + 16'd1;
                    temporary_next[7:0] = data_in;
                end else if ((opcode == 8'hf8 && step == 2) || (opcode == 8'he8 && step == 3)) begin
                    finish = 1;
                    if (opcode == 8'hf8) {registers_next.h, registers_next.l} = signed_result;
                    else registers_next.sp = signed_result;
                    registers_next.f = {2'b0, signed_nibble[4], signed_low[8], 4'b0};
                end
            end
            8'hf9: begin
                if (step == 0) registers_next.sp = {registers.h, registers.l};
                else finish = 1;
            end
            8'he9: begin finish = 1; pc_next = {registers.h, registers.l}; end
            8'hf3: begin finish = 1; disable_interrupts = 1; end
            8'hfb: begin finish = 1; enable_interrupts = 1; end
            8'hcb: begin
                access_kind = ACCESS_OPERAND;
                pc_next = pc + 16'd1;
                prefix = 1;
            end
            8'h10: begin finish = 1; stop_request = 1; end
            default: illegal = 1;
        endcase

        if (finish) begin
            access_kind = ACCESS_OPCODE;
            address = pc_next;
            write_enable = 0;
        end
    end
endmodule

`default_nettype wire
