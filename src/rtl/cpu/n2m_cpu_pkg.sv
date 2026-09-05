`default_nettype none

package n2m_cpu_pkg;
    typedef enum logic [4:0] {
        ALU_ADD = 5'd0,
        ALU_ADC = 5'd1,
        ALU_SUB = 5'd2,
        ALU_SBC = 5'd3,
        ALU_AND = 5'd4,
        ALU_XOR = 5'd5,
        ALU_OR = 5'd6,
        ALU_CP = 5'd7,
        ALU_INC = 5'd8,
        ALU_DEC = 5'd9,
        ALU_DAA = 5'd10,
        ALU_CPL = 5'd11,
        ALU_SCF = 5'd12,
        ALU_CCF = 5'd13,
        ALU_RLCA = 5'd14,
        ALU_RRCA = 5'd15,
        ALU_RLA = 5'd16,
        ALU_RRA = 5'd17,
        ALU_RLC = 5'd18,
        ALU_RRC = 5'd19,
        ALU_RL = 5'd20,
        ALU_RR = 5'd21,
        ALU_SLA = 5'd22,
        ALU_SRA = 5'd23,
        ALU_SWAP = 5'd24,
        ALU_SRL = 5'd25,
        ALU_BIT = 5'd26,
        ALU_RES = 5'd27,
        ALU_SET = 5'd28
    } alu_operation_t;
endpackage

`default_nettype wire
