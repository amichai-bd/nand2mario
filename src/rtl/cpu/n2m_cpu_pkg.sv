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
    typedef struct packed {
        logic [7:0] a;
        logic [7:0] f;
        logic [7:0] b;
        logic [7:0] c;
        logic [7:0] d;
        logic [7:0] e;
        logic [7:0] h;
        logic [7:0] l;
        logic [15:0] sp;
    } cpu_registers_t;

    typedef enum logic [2:0] {
        ACCESS_IDLE = 3'd0,
        ACCESS_OPCODE = 3'd1,
        ACCESS_OPERAND = 3'd2,
        ACCESS_DATA = 3'd3,
        ACCESS_STACK = 3'd4
    } access_kind_t;

    // Additional M-cycle address activity; unknown bits are masked, not guessed.
    typedef struct packed {
        logic valid;
        logic [15:0] address;
        logic [15:0] known_mask;
        logic write_effect;
    } cpu_address_effect_t;

    function automatic logic [7:0] read_byte(input cpu_registers_t r, input logic [2:0] index);
        case (index)
            0: read_byte = r.b;
            1: read_byte = r.c;
            2: read_byte = r.d;
            3: read_byte = r.e;
            4: read_byte = r.h;
            5: read_byte = r.l;
            7: read_byte = r.a;
            default: read_byte = 0; // (HL) is a separate bus access.
        endcase
    endfunction

    function automatic cpu_registers_t write_byte(input cpu_registers_t r, input logic [2:0] index, input logic [7:0] data);
        cpu_registers_t result;
        result = r;
        case (index)
            0: result.b = data;
            1: result.c = data;
            2: result.d = data;
            3: result.e = data;
            4: result.h = data;
            5: result.l = data;
            7: result.a = data;
            default: begin end
        endcase
        return result;
    endfunction

    function automatic logic [15:0] read_pair(input cpu_registers_t r, input logic [1:0] index, input logic stack_pair);
        case (index)
            0: read_pair = {r.b, r.c};
            1: read_pair = {r.d, r.e};
            2: read_pair = {r.h, r.l};
            default: read_pair = stack_pair ? {r.a, r.f} : r.sp;
        endcase
    endfunction

    function automatic cpu_registers_t write_pair(input cpu_registers_t r, input logic [1:0] index, input logic stack_pair, input logic [15:0] data);
        cpu_registers_t result;
        result = r;
        case (index)
            0: {result.b, result.c} = data;
            1: {result.d, result.e} = data;
            2: {result.h, result.l} = data;
            default: begin
                if (stack_pair) begin
                    result.a = data[15:8];
                    result.f = {data[7:4], 4'b0};
                end else result.sp = data;
            end
        endcase
        return result;
    endfunction

    function automatic logic condition_true(input logic [1:0] condition_code, input logic [7:0] f);
        case (condition_code)
            0: condition_true = !f[7];
            1: condition_true = f[7];
            2: condition_true = !f[4];
            default: condition_true = f[4];
        endcase
    endfunction
    typedef enum logic [2:0] {MODE_FETCH, MODE_EXECUTE, MODE_HALT, MODE_STOP, MODE_INTERRUPT, MODE_LOCK} cpu_mode_t;
    typedef struct packed {
        cpu_mode_t mode;
        logic [15:0] pc;
        logic [15:0] instruction_pc;
        logic [15:0] temporary;
        logic [15:0] irq_pc;
        logic [7:0] opcode;
        logic [23:0] fetched;
        logic [1:0] length;
        logic [2:0] step;
        logic cb_bank;
        logic ime;
        logic ime_delay;
        logic halt_bug;
        logic initialized;
        logic profile_fault;
        logic [4:0] irq_snapshot;
        logic observation_resume;
    } cpu_control_t;
endpackage
