`default_nettype none

// One execution M-cycle. The front end owns T phases, fetch overlap, reset,
// sleep and interrupt dispatch. This block never changes state itself.
module n2m_cpu_execute (
    input var n2m_cpu_pkg::cpu_execute_request_t request,
    output n2m_cpu_pkg::cpu_execute_result_t result
);

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

    n2m_cpu_alu u_alu (
        .operation(alu_operation), .lhs(alu_lhs), .rhs(alu_rhs),
        .flags_in(request.registers.f), .bit_index(request.opcode[5:3]),
        .value(alu_value), .flags_out(alu_flags)
    );

    always_comb begin
        alu_operation = n2m_cpu_pkg::ALU_ADD;
        alu_lhs = request.registers.a;
        alu_rhs = n2m_cpu_pkg::read_byte(request.registers, request.opcode[2:0]);
        if (request.opcode[2:0] == 6) alu_rhs = request.temporary[7:0];
        if (request.opcode[7:6] == 2'b10 || request.opcode[7:6] == 2'b11)
            alu_operation = {2'b0, request.opcode[5:3]};
        if (request.opcode[7:6] == 2'b11) alu_rhs = request.temporary[7:0];
        if (request.opcode[7:6] == 0 && (request.opcode[2:0] == 4 || request.opcode[2:0] == 5)) begin
            alu_operation = request.opcode[0] ? n2m_cpu_pkg::ALU_DEC : n2m_cpu_pkg::ALU_INC;
            alu_lhs = request.opcode[5:3] == 6 ? request.temporary[7:0] : n2m_cpu_pkg::read_byte(request.registers, request.opcode[5:3]);
        end
        case (request.opcode)
            8'h07: alu_operation = n2m_cpu_pkg::ALU_RLCA;
            8'h0f: alu_operation = n2m_cpu_pkg::ALU_RRCA;
            8'h17: alu_operation = n2m_cpu_pkg::ALU_RLA;
            8'h1f: alu_operation = n2m_cpu_pkg::ALU_RRA;
            8'h27: alu_operation = n2m_cpu_pkg::ALU_DAA;
            8'h2f: alu_operation = n2m_cpu_pkg::ALU_CPL;
            8'h37: alu_operation = n2m_cpu_pkg::ALU_SCF;
            8'h3f: alu_operation = n2m_cpu_pkg::ALU_CCF;
            default: begin end
        endcase
        if (request.cb_bank) begin
            alu_lhs = request.opcode[2:0] == 6 ? request.temporary[7:0] : n2m_cpu_pkg::read_byte(request.registers, request.opcode[2:0]);
            case (request.opcode[7:6])
                0: alu_operation = n2m_cpu_pkg::ALU_RLC + {2'b0, request.opcode[5:3]};
                1: alu_operation = n2m_cpu_pkg::ALU_BIT;
                2: alu_operation = n2m_cpu_pkg::ALU_RES;
                default: alu_operation = n2m_cpu_pkg::ALU_SET;
            endcase
        end
    end

    always_comb begin
        result.registers_after = request.registers;
        result.pc_after = request.pc;
        result.temporary_after = request.temporary;
        result.plan.address = request.pc;
        result.plan.write_data = 0;
        result.plan.write_enable = 0;
        result.plan.access_kind = n2m_cpu_pkg::ACCESS_IDLE;
        result.finish = 0;
        result.prefix = 0;
        result.halt_request = 0;
        result.stop_request = 0;
        result.illegal = 0;
        result.enable_interrupts = 0;
        result.disable_interrupts = 0;
        result.return_interrupt = 0;
        pair_value = n2m_cpu_pkg::read_pair(request.registers, request.opcode[5:4], 0);
        wide_pair = {1'b0, request.registers.h, request.registers.l} + {1'b0, pair_value};
        low_pair = {1'b0, request.registers.h[3:0], request.registers.l} + {1'b0, pair_value[11:0]};
        signed_result = request.registers.sp + {{8{request.temporary[7]}}, request.temporary[7:0]};
        signed_low = {1'b0, request.registers.sp[7:0]} + {1'b0, request.temporary[7:0]};
        signed_nibble = {1'b0, request.registers.sp[3:0]} + {1'b0, request.temporary[3:0]};
        taken = n2m_cpu_pkg::condition_true(request.opcode[4:3], request.registers.f);
        return_step = request.step;

        if (request.cb_bank) begin
            if (request.opcode[2:0] == 6 && request.step == 0) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_DATA;
                result.plan.address = {request.registers.h, request.registers.l};
                result.temporary_after[7:0] = request.data;
            end else if (request.opcode[2:0] == 6 && request.opcode[7:6] != 1 && request.step == 1) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_DATA;
                result.plan.address = {request.registers.h, request.registers.l};
                result.plan.write_enable = 1;
                result.plan.write_data = alu_value;
                result.registers_after.f = alu_flags;
            end else begin
                result.finish = 1;
                if (request.opcode[2:0] != 6) begin
                    result.registers_after = n2m_cpu_pkg::write_byte(request.registers, request.opcode[2:0], alu_value);
                    result.registers_after.f = alu_flags;
                end else if (request.opcode[7:6] == 1) result.registers_after.f = alu_flags;
                // Memory RMW already committed its flags with the write. In
                // RL/RR the new carry must not feed a second ALU evaluation.
            end
        end else if (request.opcode >= 8'h40 && request.opcode <= 8'h7f) begin
            if (request.opcode == 8'h76) begin
                result.finish = 1;
                result.halt_request = 1;
            end else if (request.step == 0 && (request.opcode[2:0] == 6 || request.opcode[5:3] == 6)) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_DATA;
                result.plan.address = {request.registers.h, request.registers.l};
                if (request.opcode[5:3] == 6) begin
                    result.plan.write_enable = 1;
                    result.plan.write_data = n2m_cpu_pkg::read_byte(request.registers, request.opcode[2:0]);
                end else result.temporary_after[7:0] = request.data;
            end else begin
                result.finish = 1;
                if (request.opcode[5:3] != 6)
                    result.registers_after = n2m_cpu_pkg::write_byte(request.registers, request.opcode[5:3], request.opcode[2:0] == 6 ? request.temporary[7:0] : n2m_cpu_pkg::read_byte(request.registers, request.opcode[2:0]));
            end
        end else if (request.opcode >= 8'h80 && request.opcode <= 8'hbf) begin
            if (request.opcode[2:0] == 6 && request.step == 0) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_DATA;
                result.plan.address = {request.registers.h, request.registers.l};
                result.temporary_after[7:0] = request.data;
            end else begin
                result.finish = 1;
                result.registers_after.a = alu_value;
                result.registers_after.f = alu_flags;
            end
        end else if (request.opcode[7:6] == 0 && (request.opcode[2:0] == 4 || request.opcode[2:0] == 5)) begin
            if (request.opcode[5:3] == 6 && request.step == 0) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_DATA;
                result.plan.address = {request.registers.h, request.registers.l};
                result.temporary_after[7:0] = request.data;
            end else if (request.opcode[5:3] == 6 && request.step == 1) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_DATA;
                result.plan.address = {request.registers.h, request.registers.l};
                result.plan.write_enable = 1;
                result.plan.write_data = alu_value;
                result.registers_after.f = alu_flags;
            end else begin
                result.finish = 1;
                if (request.opcode[5:3] != 6) result.registers_after = n2m_cpu_pkg::write_byte(request.registers, request.opcode[5:3], alu_value);
                result.registers_after.f = alu_flags;
            end
        end else if (request.opcode[7:6] == 0 && request.opcode[2:0] == 6) begin
            if (request.step == 0) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_OPERAND;
                result.pc_after = request.pc + 16'd1;
                result.temporary_after[7:0] = request.data;
            end else if (request.opcode[5:3] == 6 && request.step == 1) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_DATA;
                result.plan.address = {request.registers.h, request.registers.l};
                result.plan.write_enable = 1;
                result.plan.write_data = request.temporary[7:0];
            end else begin
                result.finish = 1;
                if (request.opcode[5:3] != 6) result.registers_after = n2m_cpu_pkg::write_byte(request.registers, request.opcode[5:3], request.temporary[7:0]);
            end
        end else if (request.opcode[7:6] == 0 && request.opcode[3:0] == 1) begin
            if (request.step < 2) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_OPERAND;
                result.pc_after = request.pc + 16'd1;
                if (request.step == 0) result.temporary_after[7:0] = request.data;
                else result.temporary_after[15:8] = request.data;
            end else begin
                result.finish = 1;
                result.registers_after = n2m_cpu_pkg::write_pair(request.registers, request.opcode[5:4], 0, request.temporary);
            end
        end else if (request.opcode[7:6] == 0 && (request.opcode[3:0] == 3 || request.opcode[3:0] == 11)) begin
            if (request.step == 0)
                result.registers_after = n2m_cpu_pkg::write_pair(request.registers, request.opcode[5:4], 0, request.opcode[3] ? pair_value - 16'd1 : pair_value + 16'd1);
            else result.finish = 1;
        end else if (request.opcode[7:6] == 0 && request.opcode[3:0] == 9) begin
            if (request.step == 1) begin
                result.finish = 1;
                {result.registers_after.h, result.registers_after.l} = wide_pair[15:0];
                result.registers_after.f = {request.registers.f[7], 1'b0, low_pair[12], wide_pair[16], 4'b0};
            end
        end else if (request.opcode[7:6] == 0 && request.opcode[2:0] == 2) begin
            if (request.step == 0) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_DATA;
                result.plan.address = request.opcode[5] ? {request.registers.h, request.registers.l} : n2m_cpu_pkg::read_pair(request.registers, {1'b0, request.opcode[4]}, 0);
                result.plan.write_enable = !request.opcode[3];
                result.plan.write_data = request.registers.a;
                if (request.opcode[3]) result.temporary_after[7:0] = request.data;
                if (request.opcode[5]) {result.registers_after.h, result.registers_after.l} = request.opcode[4] ? result.plan.address - 16'd1 : result.plan.address + 16'd1;
            end else begin
                result.finish = 1;
                if (request.opcode[3]) result.registers_after.a = request.temporary[7:0];
            end
        end else if (request.opcode == 8'h18 || (request.opcode & 8'he7) == 8'h20) begin
            if (request.step == 0) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_OPERAND;
                result.pc_after = request.pc + 16'd1;
                result.temporary_after[7:0] = request.data;
            end else if (request.step == 1 && (request.opcode == 8'h18 || taken))
                result.pc_after = request.pc + {{8{request.temporary[7]}}, request.temporary[7:0]};
            else result.finish = 1;
        end else if (request.opcode == 8'hc3 || (request.opcode & 8'he7) == 8'hc2 || request.opcode == 8'hcd || (request.opcode & 8'he7) == 8'hc4) begin
            if (request.step < 2) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_OPERAND;
                result.pc_after = request.pc + 16'd1;
                if (request.step == 0) result.temporary_after[7:0] = request.data;
                else result.temporary_after[15:8] = request.data;
            end else if (request.step == 2 && !(request.opcode == 8'hc3 || request.opcode == 8'hcd || taken)) result.finish = 1;
            else if (request.opcode == 8'hc3 || request.opcode[2:0] == 2) begin
                if (request.step == 2) result.pc_after = request.temporary;
                else result.finish = 1;
            end else if (request.step == 2) result.registers_after.sp = request.registers.sp - 16'd1;
            else if (request.step == 3 || request.step == 4) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_STACK;
                result.plan.address = request.registers.sp;
                result.plan.write_enable = 1;
                if (request.step == 3) begin
                    result.plan.write_data = request.pc[15:8];
                    result.registers_after.sp = request.registers.sp - 16'd1;
                end else begin
                    result.plan.write_data = request.pc[7:0];
                    result.pc_after = request.temporary;
                end
            end else result.finish = 1;
        end else if (request.opcode == 8'hc9 || request.opcode == 8'hd9 || (request.opcode & 8'he7) == 8'hc0) begin
            if ((request.opcode & 8'he7) == 8'hc0) begin
                return_step = request.step - 3'd1;
                if (!taken && request.step == 1) result.finish = 1;
            end
            if (!((request.opcode & 8'he7) == 8'hc0) || (taken && request.step != 0)) begin
                if (return_step < 2) begin
                    result.plan.access_kind = n2m_cpu_pkg::ACCESS_STACK;
                    result.plan.address = request.registers.sp;
                    result.registers_after.sp = request.registers.sp + 16'd1;
                    if (return_step == 0) result.temporary_after[7:0] = request.data;
                    else result.temporary_after[15:8] = request.data;
                end else if (return_step == 2) result.pc_after = request.temporary;
                else begin
                    result.finish = 1;
                    result.return_interrupt = request.opcode == 8'hd9;
                end
            end
        end else if ((request.opcode & 8'hcf) == 8'hc5 || (request.opcode & 8'hc7) == 8'hc7) begin
            pair_value = n2m_cpu_pkg::read_pair(request.registers, request.opcode[5:4], 1);
            if (request.step == 0) result.registers_after.sp = request.registers.sp - 16'd1;
            else if (request.step == 1 || request.step == 2) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_STACK;
                result.plan.address = request.registers.sp;
                result.plan.write_enable = 1;
                if (request.step == 1) begin
                    result.plan.write_data = request.opcode[1] ? request.pc[15:8] : pair_value[15:8];
                    result.registers_after.sp = request.registers.sp - 16'd1;
                end else begin
                    result.plan.write_data = request.opcode[1] ? request.pc[7:0] : pair_value[7:0];
                    if (request.opcode[1]) result.pc_after = {10'b0, request.opcode[5:3], 3'b0};
                end
            end else result.finish = 1;
        end else if ((request.opcode & 8'hcf) == 8'hc1) begin
            if (request.step < 2) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_STACK;
                result.plan.address = request.registers.sp;
                result.registers_after.sp = request.registers.sp + 16'd1;
                if (request.step == 0) result.temporary_after[7:0] = request.data;
                else result.temporary_after[15:8] = request.data;
            end else begin
                result.finish = 1;
                result.registers_after = n2m_cpu_pkg::write_pair(request.registers, request.opcode[5:4], 1, request.temporary);
            end
        end else if ((request.opcode & 8'hc7) == 8'hc6) begin
            if (request.step == 0) begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_OPERAND;
                result.pc_after = request.pc + 16'd1;
                result.temporary_after[7:0] = request.data;
            end else begin
                result.finish = 1;
                result.registers_after.a = alu_value;
                result.registers_after.f = alu_flags;
            end
        end else case (request.opcode)
            8'h00: result.finish = 1;
            8'h07, 8'h0f, 8'h17, 8'h1f, 8'h27, 8'h2f, 8'h37, 8'h3f: begin
                result.finish = 1;
                result.registers_after.a = alu_value;
                result.registers_after.f = alu_flags;
            end
            8'h08, 8'hea, 8'hfa: begin
                if (request.step < 2) begin
                    result.plan.access_kind = n2m_cpu_pkg::ACCESS_OPERAND;
                    result.pc_after = request.pc + 16'd1;
                    if (request.step == 0) result.temporary_after[7:0] = request.data;
                    else result.temporary_after[15:8] = request.data;
                end else if (request.step == 2 || (request.opcode == 8'h08 && request.step == 3)) begin
                    result.plan.access_kind = n2m_cpu_pkg::ACCESS_DATA;
                    result.plan.address = request.temporary;
                    if (request.step == 3) result.plan.address = request.temporary + 16'd1;
                    result.plan.write_enable = request.opcode != 8'hfa;
                    result.plan.write_data = request.registers.a;
                    if (request.opcode == 8'h08) result.plan.write_data = request.step == 2 ? request.registers.sp[7:0] : request.registers.sp[15:8];
                    if (request.opcode == 8'hfa) result.temporary_after[7:0] = request.data;
                end else begin
                    result.finish = 1;
                    if (request.opcode == 8'hfa) result.registers_after.a = request.temporary[7:0];
                end
            end
            8'he0, 8'hf0, 8'he2, 8'hf2: begin
                if (!request.opcode[1] && request.step == 0) begin
                    result.plan.access_kind = n2m_cpu_pkg::ACCESS_OPERAND;
                    result.pc_after = request.pc + 16'd1;
                    result.temporary_after[7:0] = request.data;
                end else if ((!request.opcode[1] && request.step == 1) || (request.opcode[1] && request.step == 0)) begin
                    result.plan.access_kind = n2m_cpu_pkg::ACCESS_DATA;
                    result.plan.address = {8'hff, request.opcode[1] ? request.registers.c : request.temporary[7:0]};
                    result.plan.write_enable = !request.opcode[4];
                    result.plan.write_data = request.registers.a;
                    if (request.opcode[4]) result.temporary_after[7:0] = request.data;
                end else begin
                    result.finish = 1;
                    if (request.opcode[4]) result.registers_after.a = request.temporary[7:0];
                end
            end
            8'he8, 8'hf8: begin
                if (request.step == 0) begin
                    result.plan.access_kind = n2m_cpu_pkg::ACCESS_OPERAND;
                    result.pc_after = request.pc + 16'd1;
                    result.temporary_after[7:0] = request.data;
                end else if ((request.opcode == 8'hf8 && request.step == 2) || (request.opcode == 8'he8 && request.step == 3)) begin
                    result.finish = 1;
                    if (request.opcode == 8'hf8) {result.registers_after.h, result.registers_after.l} = signed_result;
                    else result.registers_after.sp = signed_result;
                    result.registers_after.f = {2'b0, signed_nibble[4], signed_low[8], 4'b0};
                end
            end
            8'hf9: begin
                if (request.step == 0) result.registers_after.sp = {request.registers.h, request.registers.l};
                else result.finish = 1;
            end
            8'he9: begin result.finish = 1; result.pc_after = {request.registers.h, request.registers.l}; end
            8'hf3: begin result.finish = 1; result.disable_interrupts = 1; end
            8'hfb: begin result.finish = 1; result.enable_interrupts = 1; end
            8'hcb: begin
                result.plan.access_kind = n2m_cpu_pkg::ACCESS_OPERAND;
                result.pc_after = request.pc + 16'd1;
                result.prefix = 1;
            end
            8'h10: begin result.finish = 1; result.stop_request = 1; end
            default: result.illegal = 1;
        endcase

        // Expose only additional IDU activity. Ordinary transactions retain
        // their separate read/write kind. The front end owns final-fetch PC
        // increments, including HALT-bug and interrupt-discard exceptions.
        result.address_effect = '0;
        if (result.plan.access_kind == n2m_cpu_pkg::ACCESS_OPERAND) begin
            result.address_effect.valid = 1;
            result.address_effect.address = request.pc;
        end
        if (!request.cb_bank) begin
            if (request.opcode[7:6] == 0 && (request.opcode[3:0] == 3 || request.opcode[3:0] == 11) && request.step == 0) begin
                result.address_effect.valid = 1;
                result.address_effect.address = n2m_cpu_pkg::read_pair(request.registers, request.opcode[5:4], 0);
            end
            if (request.opcode[7:6] == 0 && request.opcode[2:0] == 2 && request.opcode[5] && request.step == 0) begin
                result.address_effect.valid = 1;
                result.address_effect.address = {request.registers.h, request.registers.l};
            end
            if ((request.opcode == 8'h18 || (request.opcode & 8'he7) == 8'h20) && request.step == 1 && !result.finish) begin
                result.address_effect.valid = 1;
                result.address_effect.address = {request.pc[15:8], 8'b0};
            end
            if (((request.opcode & 8'hcf) == 8'hc5 || (request.opcode & 8'hc7) == 8'hc7) && request.step < 2) begin
                result.address_effect.valid = 1;
                result.address_effect.address = request.registers.sp;
            end
            if ((request.opcode == 8'hcd || (request.opcode & 8'he7) == 8'hc4) && !result.finish && (request.step == 2 || request.step == 3)) begin
                result.address_effect.valid = 1;
                result.address_effect.address = request.registers.sp;
            end
            if (request.opcode == 8'h08 && request.step == 2) begin
                result.address_effect.valid = 1;
                result.address_effect.address = request.temporary;
            end
            if (request.opcode == 8'hf9 && request.step == 0) begin
                result.address_effect.valid = 1;
                result.address_effect.address = {request.registers.h, request.registers.l};
            end
            if ((request.opcode & 8'hcf) == 8'hc1 && request.step == 0) begin
                result.address_effect.valid = 1;
                result.address_effect.address = request.registers.sp;
            end
            if ((request.opcode == 8'hc9 || request.opcode == 8'hd9 || (request.opcode & 8'he7) == 8'hc0) &&
                    result.plan.access_kind == n2m_cpu_pkg::ACCESS_STACK && return_step == 0) begin
                result.address_effect.valid = 1;
                result.address_effect.address = request.registers.sp;
            end
        end
        if (result.address_effect.valid) begin
            result.address_effect.known_mask = 16'hffff;
            result.address_effect.write_effect = 1;
            if (!request.cb_bank && (request.opcode == 8'h18 || (request.opcode & 8'he7) == 8'h20) && request.step == 1 && !result.finish)
                result.address_effect.known_mask = 16'hff00;
        end

        if (result.finish) begin
            result.plan.access_kind = n2m_cpu_pkg::ACCESS_OPCODE;
            result.plan.address = result.pc_after;
            result.plan.write_enable = 0;
        end
    end
endmodule
