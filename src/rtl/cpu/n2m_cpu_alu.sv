`default_nettype none

// Pure instruction datapath. The CPU owner controls timing and writeback.
module n2m_cpu_alu (
    input  var logic [4:0] operation,
    input  var logic [7:0] lhs,
    input  var logic [7:0] rhs,
    input  var logic [7:0] flags_in,
    input  var logic [2:0] bit_index,
    output logic [7:0] value,
    output logic [7:0] flags_out
);

    logic [8:0] wide_result;
    logic [4:0] low_result;
    logic [7:0] adjustment;
    logic carry_in;
    logic carry_out;

    always_comb begin
        value = lhs;
        flags_out = {flags_in[7:4], 4'b0000};
        wide_result = 9'b0;
        low_result = 5'b0;
        adjustment = 8'b0;
        carry_in = 1'b0;
        carry_out = flags_in[4];
        case (operation)
            n2m_cpu_pkg::ALU_ADD, n2m_cpu_pkg::ALU_ADC: begin // ADD, ADC
                carry_in = (operation == n2m_cpu_pkg::ALU_ADC) && flags_in[4];
                wide_result = {1'b0, lhs} + {1'b0, rhs} + {8'b0, carry_in};
                low_result = {1'b0, lhs[3:0]} + {1'b0, rhs[3:0]} + {4'b0, carry_in};
                value = wide_result[7:0];
                flags_out = {value == 8'b0, 1'b0, low_result[4], wide_result[8], 4'b0};
            end
            n2m_cpu_pkg::ALU_SUB, n2m_cpu_pkg::ALU_SBC, n2m_cpu_pkg::ALU_CP: begin // SUB, SBC, CP
                carry_in = (operation == n2m_cpu_pkg::ALU_SBC) && flags_in[4];
                wide_result = {1'b0, lhs} - {1'b0, rhs} - {8'b0, carry_in};
                low_result = {1'b0, lhs[3:0]} - {1'b0, rhs[3:0]} - {4'b0, carry_in};
                value = wide_result[7:0];
                flags_out = {value == 8'b0, 1'b1, low_result[4], wide_result[8], 4'b0};
                if (operation == n2m_cpu_pkg::ALU_CP) value = lhs;
            end
            n2m_cpu_pkg::ALU_AND, n2m_cpu_pkg::ALU_XOR, n2m_cpu_pkg::ALU_OR: begin // AND, XOR, OR
                case (operation)
                    n2m_cpu_pkg::ALU_AND: value = lhs & rhs;
                    n2m_cpu_pkg::ALU_XOR: value = lhs ^ rhs;
                    default: value = lhs | rhs;
                endcase
                flags_out = {value == 8'b0, 1'b0, operation == n2m_cpu_pkg::ALU_AND, 1'b0, 4'b0};
            end
            n2m_cpu_pkg::ALU_INC: begin // INC preserves C.
                value = lhs + 8'd1;
                flags_out = {value == 8'b0, 1'b0, lhs[3:0] == 4'hf, flags_in[4], 4'b0};
            end
            n2m_cpu_pkg::ALU_DEC: begin // DEC preserves C.
                value = lhs - 8'd1;
                flags_out = {value == 8'b0, 1'b1, lhs[3:0] == 4'h0, flags_in[4], 4'b0};
            end
            n2m_cpu_pkg::ALU_DAA: begin // DAA uses N to distinguish add/subtract correction.
                if (flags_in[4] || (!flags_in[6] && lhs > 8'h99)) begin
                    adjustment = 8'h60;
                    carry_out = 1'b1;
                end
                if (flags_in[5] || (!flags_in[6] && lhs[3:0] > 4'd9))
                    adjustment = adjustment | 8'h06;
                if (flags_in[6]) value = lhs - adjustment;
                else value = lhs + adjustment;
                flags_out = {value == 8'b0, flags_in[6], 1'b0, carry_out, 4'b0};
            end
            n2m_cpu_pkg::ALU_CPL: begin // CPL preserves Z/C.
                value = ~lhs;
                flags_out = {flags_in[7], 2'b11, flags_in[4], 4'b0};
            end
            n2m_cpu_pkg::ALU_SCF: flags_out = {flags_in[7], 2'b00, 1'b1, 4'b0}; // SCF
            n2m_cpu_pkg::ALU_CCF: flags_out = {flags_in[7], 2'b00, ~flags_in[4], 4'b0}; // CCF
            n2m_cpu_pkg::ALU_RLCA, n2m_cpu_pkg::ALU_RLC: begin // RLCA, RLC
                value = {lhs[6:0], lhs[7]};
                flags_out = {(operation == n2m_cpu_pkg::ALU_RLC) && value == 0, 2'b00, lhs[7], 4'b0};
            end
            n2m_cpu_pkg::ALU_RRCA, n2m_cpu_pkg::ALU_RRC: begin // RRCA, RRC
                value = {lhs[0], lhs[7:1]};
                flags_out = {(operation == n2m_cpu_pkg::ALU_RRC) && value == 0, 2'b00, lhs[0], 4'b0};
            end
            n2m_cpu_pkg::ALU_RLA, n2m_cpu_pkg::ALU_RL: begin // RLA, RL
                value = {lhs[6:0], flags_in[4]};
                flags_out = {(operation == n2m_cpu_pkg::ALU_RL) && value == 0, 2'b00, lhs[7], 4'b0};
            end
            n2m_cpu_pkg::ALU_RRA, n2m_cpu_pkg::ALU_RR: begin // RRA, RR
                value = {flags_in[4], lhs[7:1]};
                flags_out = {(operation == n2m_cpu_pkg::ALU_RR) && value == 0, 2'b00, lhs[0], 4'b0};
            end
            n2m_cpu_pkg::ALU_SLA: begin // SLA
                value = {lhs[6:0], 1'b0};
                flags_out = {value == 0, 2'b00, lhs[7], 4'b0};
            end
            n2m_cpu_pkg::ALU_SRA: begin // SRA
                value = {lhs[7], lhs[7:1]};
                flags_out = {value == 0, 2'b00, lhs[0], 4'b0};
            end
            n2m_cpu_pkg::ALU_SWAP: begin // SWAP
                value = {lhs[3:0], lhs[7:4]};
                flags_out = {value == 0, 7'b0};
            end
            n2m_cpu_pkg::ALU_SRL: begin // SRL
                value = {1'b0, lhs[7:1]};
                flags_out = {value == 0, 2'b00, lhs[0], 4'b0};
            end
            n2m_cpu_pkg::ALU_BIT: flags_out = {~lhs[bit_index], 1'b0, 1'b1, flags_in[4], 4'b0};
            n2m_cpu_pkg::ALU_RES: value = lhs & ~(8'b1 << bit_index);
            n2m_cpu_pkg::ALU_SET: value = lhs | (8'b1 << bit_index);
            default: begin
                value = lhs;
                flags_out = {flags_in[7:4], 4'b0};
            end
        endcase
    end
endmodule
