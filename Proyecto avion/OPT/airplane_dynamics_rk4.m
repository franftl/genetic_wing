function [x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_rk4(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner)
% airplane_dynamics_opt:
% VERSIÓN OPTIMIZADA CON RK4: La física se mantiene 100% idéntica.

    % --- Estado inicial para RK4: Y = [x; y; z; v_x; v_y; v_z; yaw_rad] ---
    Y0 = [x; y; z; v_x; v_y; v_z; yaw_rad];
    
    % Evaluamos k1. Extraemos las variables físicas para mantener tu loggeo intacto.
    [k1, a_log, cl_log, cd_total_log, drag_log, Thrust_N_log, LIFT_vec_log, THRUST_vec_log, DRAG_vec_log, Motor_fila_log] = calc_derivs(Y0);
    
    % Evaluamos los siguientes pasos de RK4 (descartando los logs intermedios)
    [k2, ~, ~, ~, ~, ~, ~, ~, ~, ~] = calc_derivs(Y0 + 0.5 * t_n * k1);
    [k3, ~, ~, ~, ~, ~, ~, ~, ~, ~] = calc_derivs(Y0 + 0.5 * t_n * k2);
    [k4, ~, ~, ~, ~, ~, ~, ~, ~, ~] = calc_derivs(Y0 + t_n * k3);
    
    % --- Actualización RK4 ---
    Y_new = Y0 + (t_n/6) * (k1 + 2*k2 + 2*k3 + k4);
    
    % Desempaquetar el nuevo estado
    x = Y_new(1); y = Y_new(2); z = Y_new(3);
    v_x = Y_new(4); v_y = Y_new(5); v_z = Y_new(6);
    yaw_rad = Y_new(7);
    
    % --- Actualización de Energía y Loggeo ---
    % Se utiliza la corriente al inicio del step (evaluada en k1), igual que en tu original.
    Energy = Energy + Motor_fila_log.current * t_n / 3600;
    
    % FIX #16: Se mantiene la estructura exacta de tu array 'inform'
    inform = [inform [x; y; z; v_x; v_y; v_z; a_log(1,1); a_log(2,1); a_log(3,1); t; cl_log; cd_total_log; drag_log; Thrust_N_log; ...
                     LIFT_vec_log(1); LIFT_vec_log(2); LIFT_vec_log(3); ...
                     THRUST_vec_log(1); THRUST_vec_log(2); THRUST_vec_log(3); ...
                     DRAG_vec_log(1); DRAG_vec_log(2); DRAG_vec_log(3)]];
                     
    t = t + t_n;

    % =========================================================================
    % FUNCIÓN ANIDADA: Contiene EXACTAMENTE tu física y matrices
    % =========================================================================
    function [dY, a, cl, cd_total, drag, Thrust_N, LIFT_vec, THRUST_vec, DRAG_vec, Motor_fila] = calc_derivs(Y_in)
        % Desempaquetar estado de prueba
        sys_x = Y_in(1); sys_y = Y_in(2); sys_z = Y_in(3);
        sys_vx = Y_in(4); sys_vy = Y_in(5); sys_vz = Y_in(6);
        sys_yaw = Y_in(7);
        
        % --- Matrices de Rotación (FIX #12) ---
        cos_p=cos(pitch_rad);
        sin_p=sin(pitch_rad);
        T_pitch=[ cos_p  0 -sin_p;
                  0      1  0;
                 sin_p  0  cos_p];
            
        cos_r=cos(roll_rad);
        sin_r=sin(roll_rad);
        T_roll=[ 1   0    0;
                 0  cos_r  -sin_r;
                 0  sin_r   cos_r];
            
        cos_y=cos(sys_yaw);
        sin_y=sin(sys_yaw);
        T_yaw=[  cos_y   -sin_y  0;
                 sin_y    cos_y  0;
                   0        0    1];
               
        % --- Interpoladores (OPTIMIZADO) ---
        [~, Motor_fila] = motor(MOTOR_TABLE, throttle); 
        PROP_STRUCT = PROP_TABLE; 
        v = sqrt(sys_vx^2 + sys_vy^2 + sys_vz^2);
        v_safe = max(v, 1e-6);
        v_normal_helice = abs(dot(T_yaw*T_pitch*T_roll* [1;0;0], [sys_vx;sys_vy;sys_vz]));
        Prop_fila = interpProp(PROP_STRUCT, v_normal_helice, Motor_fila.rotation_speed);
        
        v_safe_sq = max(v^2, 1e-6);
        cos_p_safe = max(cos_p, 1e-6);
        cos_r_safe = max(cos_r, 1e-6);
        
        % --- FIX #2 (Corregido) y #15b ---
        g = 9.81;
        lift_required = (MTOW * g) / (cos_r_safe * cos_p_safe);
        cl = (2 * lift_required) / (ro * v_safe_sq * S_ref);
         
        [~, Avion_fila] = avion_cl(AVION_TABLE, cl);
        
        % --- Fuerzas ---
        % FIX #8: El cd del archivo ya incluye la inducida, solo sumamos el cd0 extra.
        cd_total = Avion_fila.c_d + cd0;
        lift = 0.5*ro*S_ref*cl*v_safe_sq;
        drag = 0.5*ro*S_ref*cd_total*v_safe_sq + 0.5*(S_Banner)*ro*(cd_Banner)*v^2;
        Thrust_N = Prop_fila.Thrust_N;
        
        % --- Ecuaciones de Movimiento ---
        V_versor = [sys_vx; sys_vy; sys_vz] / v_safe;
        % --- FIX #7: Modelo Híbrido ---
        a = [0;0;-g] + T_yaw*T_pitch*T_roll * [ Thrust_N/MTOW ; 0; lift/MTOW ] - (drag/MTOW)*V_versor;
        
        % --- Vectores 3D para loggeo ---
        THRUST_vec = T_yaw*T_pitch*T_roll * [ Thrust_N ; 0; 0 ];
        LIFT_vec   = T_yaw*T_pitch*T_roll * [ 0 ; 0; lift ];
        DRAG_vec   = -drag * V_versor;
        
        % --- Actualización de Yaw (Modelo Inestable Original) ---
        vx2_vy2 = sys_vx^2 + sys_vy^2;
        safe_den = max(vx2_vy2, 1e-12); 
        yaw_dot = (sys_vx*a(2) - sys_vy*a(1)) / safe_den;
        
        % --- Derivada de Estado (Velocidades, Aceleraciones, Yaw_dot) ---
        dY = [sys_vx; sys_vy; sys_vz; a(1); a(2); a(3); yaw_dot];
    end
end