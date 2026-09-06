`default_nettype none

// Independent integer reference from the CPU owner instruction rules.
// It does not import product enum values, decode, or ALU implementation.
package cpu_alu_reference;
    function automatic logic [15:0] calculate(
        input integer op, a, b, f, bit_number
    );
        integer answer;
        integer result_byte;
        integer z;
        integer n;
        integer h;
        integer c;
        integer old_c;
        integer amount;
        integer mask;
        begin
            answer = a;
            z = (f / 128) % 2;
            n = (f / 64) % 2;
            h = (f / 32) % 2;
            c = (f / 16) % 2;
            old_c = c;
            amount = 0;
            mask = 2 ** bit_number;
            case (op)
                0, 1: begin
                    amount = (op == 1) ? old_c : 0;
                    answer = a + b + amount;
                    h = ((a % 16) + (b % 16) + amount) > 15;
                    c = answer > 255;
                    n = 0;
                    z = (answer % 256) == 0;
                end
                2, 3, 7: begin
                    amount = (op == 3) ? old_c : 0;
                    answer = a - b - amount;
                    h = (a % 16) < ((b % 16) + amount);
                    c = a < (b + amount);
                    n = 1;
                    z = (answer & 255) == 0;
                    if (op == 7) answer = a;
                end
                4, 5, 6: begin
                    if (op == 4) answer = a & b;
                    else if (op == 5) answer = a ^ b;
                    else answer = a | b;
                    z = answer == 0;
                    n = 0;
                    h = op == 4;
                    c = 0;
                end
                8: begin
                    answer = a + 1;
                    z = (answer % 256) == 0;
                    n = 0;
                    h = (a % 16) == 15;
                end
                9: begin
                    answer = a - 1;
                    z = answer == 0;
                    n = 1;
                    h = (a % 16) == 0;
                end
                10: begin
                    // Decimal correction is selected using integer thresholds.
                    // Subtraction never derives a new carry from the byte.
                    if (n != 0) begin
                        answer = a - (96 * old_c) - (6 * h);
                    end else begin
                        if ((a % 16) >= 10 || h != 0) amount = 6;
                        c = (a >= 154) || old_c;
                        answer = a + amount + (96 * c);
                    end
                    z = (answer & 255) == 0;
                    h = 0;
                end
                11: begin answer = 255 - a; n = 1; h = 1; end
                12: begin n = 0; h = 0; c = 1; end
                13: begin n = 0; h = 0; c = 1 - old_c; end
                14, 18: begin answer = ((a * 2) % 256) + (a / 128); c = a / 128; end
                15, 19: begin answer = (a / 2) + (128 * (a % 2)); c = a % 2; end
                16, 20: begin answer = ((a * 2) % 256) + old_c; c = a / 128; end
                17, 21: begin answer = (a / 2) + (128 * old_c); c = a % 2; end
                22: begin answer = (a * 2) % 256; c = a / 128; end
                23: begin answer = (a / 2) + (128 * (a / 128)); c = a % 2; end
                24: begin answer = (a / 16) + (16 * (a % 16)); c = 0; end
                25: begin answer = a / 2; c = a % 2; end
                26: begin z = ((a / mask) % 2) == 0; n = 0; h = 1; end
                27: if (((a / mask) % 2) != 0) answer = a - mask;
                28: if (((a / mask) % 2) == 0) answer = a + mask;
                default: begin end
            endcase
            if (op >= 14 && op <= 25) begin
                z = (op >= 18) && answer == 0;
                n = 0;
                h = 0;
            end
            result_byte = answer & 255;
            calculate = 16'((result_byte * 256) + (z * 128) + (n * 64) + (h * 32) + (c * 16));
        end
    endfunction
endpackage

