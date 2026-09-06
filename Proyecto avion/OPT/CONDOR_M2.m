clc
clear
close all
disp('M2');
% =========================================================================
% --- CONFIGURACIÓN DE LA SIMULACIÓN ---
% =========================================================================
n_patitos=151;
n_cargo=4;




% throttle=1600 ;%1576
% prop1="PER3_20x15E.dat";
% v_x=26;






throttle=1930 ;
prop1="PER3_20x11E.dat";
v_x=32;%9.7/8.5-12.55


MTOW=13.4;      %Por dios tocar


ro=1.255;
S_ref=1.386;
S=8;
cd0=0.016;
t_n=0.04;
% --- Banner
l_Banner=0;
S_Banner=0;
cd_Banner=0;
% --- Archivos de Datos ---

motor1='Scorpion A-5025-310kv.dat';
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
%yaw_rad=deg2rad(180);

%% Pierna #2
x0=x; y0=y;
disp("Pierna   #2 ñeri")
while sqrt((x-x0)^2+(y-y0)^2)<130
    pitch_rad=0;
    roll_rad=deg2rad(0);
    %yaw_rad=deg2rad(180);
[x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_opt(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner);
end

%% AutoGyro #2
roll_rad_obj=deg2rad(roll_2);
t_obj=1;
roll_dif=-roll_rad_obj+roll_rad;
disp("AutoGyro 2a ñeri")
while  abs(roll_rad - roll_rad_obj) > deg2rad(2)
    pitch_rad=0;
    roll_rad=roll_rad-t_n*(roll_dif)/t_obj;
[x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_opt(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner);
end
disp("AutoGyro 2b ñeri")
% OJO: El objetivo de yaw aquí (-500) es lo mismo que (-140)
% roll_2 es -73, girará a la izquierda (negativo)
while abs(yaw_rad - deg2rad(360+180-13)) > deg2rad(2) % Corregido de -520 a -140
    %rad2deg((yaw_rad - deg2rad(360)))
    
    pitch_rad=0;
[x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_opt(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner);
end
roll_rad_obj=deg2rad(0);
t_obj=1;
roll_dif=-roll_rad_obj+roll_rad;
disp("AutoGyro 2c ñeri")
while  abs(roll_rad - roll_rad_obj) > deg2rad(2)
    pitch_rad=0;
    roll_rad=roll_rad+t_n*(-roll_dif)/t_obj;
[x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_opt(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner);
end

%% Pierna #3
x0=x; y0=y;
roll_rad=0;
disp("Pierna   #3 ñeri")
while sqrt((x-x0)^2+(y-y0)^2)<90
    pitch_rad=0;
    roll_rad=0;
[x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_opt(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner);
end

%% AUTO Giro #3
roll_rad_obj=deg2rad(roll_3);
t_obj=1;
roll_dif=-roll_rad_obj+roll_rad;
disp("AutoGyro 3a ñeri")
while  abs(roll_rad - roll_rad_obj) > deg2rad(2)
    pitch_rad=0;
    roll_rad=roll_rad+t_n*(-roll_dif)/t_obj;
[x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_opt(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner);
end
disp("AutoGyro 3b ñeri")
while abs(yaw_rad - deg2rad(-13+720)) > deg2rad(5)

    pitch_rad=0;
[x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_opt(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner);
end
roll_rad_obj=deg2rad(0);
t_obj=1;
roll_dif=roll_rad-roll_rad_obj;
disp("AutoGyro 3c ñeri")
while  abs(roll_rad - roll_rad_obj) > deg2rad(2)
    pitch_rad=0;

    roll_rad=roll_rad+t_n*(-roll_dif)/t_obj;
[x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_opt(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner);
end

%% Pierna #4
x0=0; y0=y;
disp("Pierna    #4 ñeri")
while sqrt((x-x0)^2+0*(y-y0)^2)>5
    pitch_rad=0;
    roll_rad=0;
[x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,inform,Energy,t] = airplane_dynamics_opt(MTOW,t_n,ro,S_ref,x,y,z,v_x,v_y,v_z,roll_rad,pitch_rad,yaw_rad,throttle,cd0, ...
                                                                                          PROP_TABLE, MOTOR_TABLE, AVION_TABLE, ...
                                                                                          inform,Energy,t,S_Banner,cd_Banner);
end
clc
% =========================================================================
%% --- GRÁFICOS Y RESULTADOS ---
% =========================================================================
% --- Llamada a la nueva función de ploteo ---
% Pasamos todos los parámetros necesarios para los gráficos y el resumen
%plot_results(inform, t, Energy, S, plane1, motor1, prop1, MTOW, throttle, t_n);
plot_results_report(inform, t, Energy, S, plane1, motor1, prop1, MTOW, throttle, t_n);



% =========================================================================
%% --- REPORTE DE PUNTAJE EN CONSOLA ---
% =========================================================================


% --- Constantes de Ingresos (Table 3.3.3.2) ---
Ip1 = 6;    % Fixed income per passenger
Ip2 = 2;    % Income per passenger per lap
Ic1 = 10;   % Fixed income per cargo
Ic2 = 8;    % Income per cargo per lap

% --- Constantes de Costos (Table 3.3.3.2) ---
Ce = 10;    % Base operating cost per lap
Cp = 0.5;   % Passenger operating cost per lap
Cc = 2;     % Cargo operating cost per lap


EF=1;
% 2. Income
laps=int32(5*60/t-1);
Income = (n_patitos * (Ip1 + (Ip2 * laps))) + ...
         (n_cargo * (Ic1 + (Ic2 * laps)));

% 3. Cost
Cost = laps * (Ce + (n_patitos * Cp) + (n_cargo * Cc)) * EF;

% 4. Net Income
Net_Income = Income - Cost;
fprintf('\n============================================\n');
fprintf('      MISSION 2 SCORE: CHARTER FLIGHT       \n');
fprintf('============================================\n');
fprintf(' Passengers:  %d\n', n_patitos);
fprintf(' Cargo units: %d\n', n_cargo);
fprintf(' Laps flown:  %d\n', laps);
fprintf('--------------------------------------------\n');
fprintf(' TOTAL INCOME: $ %.2f\n', Income);
fprintf(' TOTAL COST:   $ %.2f\n', Cost);
fprintf('--------------------------------------------\n');
fprintf(' >> NET INCOME: $ %.2f <<\n', Net_Income);
fprintf('============================================\n\n');