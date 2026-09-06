clc
clear
close all
disp('M1');
% =========================================================================
% --- CONFIGURACIÓN DE LA SIMULACIÓN ---
% =========================================================================
MTOW=0.9;      %Por dios tocar
ro=1.255;
S_ref=0.34;
S=3;
cd0=0.4;
t_n=0.02;
% --- Banner
l_Banner=0;
S_Banner=0;
cd_Banner=0;



throttle=2000 ;
prop1="PER3_10x45mr.dat";
v_x=8;%9.7/8.5-34.63
% --- Archivos de Datos ---

motor1='A2212_13T_1000KV.dat';
plane1='CONDOR.dat';

% --- Plan de Vuelo ---
roll_1 = -60; 
roll_2 = -60;
roll_3 = -60;




% =========================================================================
% --- OPTIMIZACIÓN: Cargar archivos UNA SOLA VEZ ---
% =========================================================================
disp('Cargando archivos de datos (una sola vez)...');

PROP_TABLE = prop(prop1);

MOTOR_TABLE = motor(motor1);
MOTOR_TABLE.torque = abs(MOTOR_TABLE.torque);
AVION_TABLE = avion_cl(plane1);
disp('Archivos cargados en memoria.');

% =========================================================================
%% --- CONDICIONES INICIALES (t=0) ---
% =========================================================================
t=0;
x=0; y=0; z=0;
 v_y=0; v_z=0;
Energy=0;
pitch_rad=deg2rad(0);
roll_rad=deg2rad(0);
yaw_rad=deg2rad(0);

inform =[];

%% Despegue (Sección comentada)
while pitch_rad>-0.5
    break
    % ... (código de despegue omitido) ...
end
pitch_rad=0;

% =========================================================================
%% --- BUCLE DE SIMULACIÓN ---
% =========================================================================

%% Pierna #1
x0=x; y0=y;
disp("Pierna   #1 ñeri")
while sqrt((x-x0)^2+(y-y0)^2)<100
    pitch_rad=0;
    % --- LLAMADA OPTIMIZADA ---
    % Pasamos las TABLAS (ej: PROP_TABLE) en lugar de los NOMBRES (ej: prop1)
[x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_opt(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner);
end
pitch_rad=0;

%% AUTO Giro #1
roll_rad_obj=deg2rad(roll_1);
t_obj=1;
roll_dif=-roll_rad_obj+roll_rad;
disp("AutoGyro 1a ñeri")
while  abs(roll_rad - roll_rad_obj) > deg2rad(2)
    pitch_rad=0;
    roll_rad=roll_rad+t_n*(-roll_dif)/t_obj;
[x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_opt(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner);
end
disp("AutoGyro 1b ñeri")
while abs(yaw_rad - deg2rad(180-13)) > deg2rad(2)
    pitch_rad=0;
[x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_opt(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner);
end
roll_rad_obj=deg2rad(0);
t_obj=1;
roll_dif=roll_rad-roll_rad_obj;
disp("AutoGyro 1c ñeri")
while  abs(roll_rad - roll_rad_obj) > deg2rad(2)
    pitch_rad=0;
    roll_rad=roll_rad+t_n*(-roll_dif)/t_obj;
[x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_opt(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner);
end
roll_rad=deg2rad(0);
yaw_rad=deg2rad(180);

%% Pierna #2
x0=x; y0=y;
disp("Pierna   #2 ñeri")
while sqrt((x-x0)^2+(y-y0)^2)<130
    pitch_rad=0;
    roll_rad=deg2rad(0);
    yaw_rad=deg2rad(180);
[x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_opt(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner);
end



% =========================================================================
%% --- GRÁFICOS Y RESULTADOS ---
% =========================================================================
% --- Llamada a la nueva función de ploteo ---
% Pasamos todos los parámetros necesarios para los gráficos y el resumen
%plot_results(inform, t, Energy, S, plane1, motor1, prop1, MTOW, throttle, t_n);
plot_results_report(inform, t, Energy, S, plane1, motor1, prop1, MTOW, throttle, t_n);


