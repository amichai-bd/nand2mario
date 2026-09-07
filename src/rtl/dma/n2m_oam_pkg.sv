`default_nettype none
package n2m_oam_pkg;
    typedef enum logic [1:0] {
        OAM_NONE, OAM_READ, OAM_WRITE, OAM_READ_WRITE
    } oam_effect_t;
endpackage
