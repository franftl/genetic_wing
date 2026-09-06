clc
clear
% =========================================================================
%% --- REPORTE DE PUNTAJE EN CONSOLA ---
% =========================================================================

nombre_mision = 'Carga, patitos y 2 vueltas'; 
laps=2;
n_patitos=151;
n_cargo=4;%18
EF=1;


% nombre_mision = 'Posible rival'; 
% laps=6;
% n_patitos=40;
% n_cargo=10;%18
%EF=1;



% nombre_mision = 'Carga, patitos y 4 vueltas'; 
% laps=4;
% n_patitos=151-6;
% n_cargo=8;%18

% nombre_mision = 'Sin carga, patitos y 4 vueltas'; 
% laps=4;
% n_patitos=151;
% n_cargo=1;


% nombre_mision = 'Posible rival'; 
% laps=12;
% n_patitos=6;
% n_cargo=2;
% 
% 
% nombre_mision = 'rival Pesado'; 
% laps=8;
% n_patitos=40;
% n_cargo=39/3;

nombre_mision = 'dbf_uw'; 
laps=12;
n_patitos=3;
n_cargo=1;
EF=3



nombre_mision = 'M2 TEST'; 
laps=5;
n_patitos=151-12;
n_cargo=4;%18
EF=1;


% --- Constantes de Ingresos (Table 3.3.3.2) ---
Ip1 = 6;    % Fixed income per passenger
Ip2 = 2;    % Income per passenger per lap
Ic1 = 10;   % Fixed income per cargo
Ic2 = 8;    % Income per cargo per lap

% --- Constantes de Costos (Table 3.3.3.2) ---
Ce = 10;    % Base operating cost per lap
Cp = 0.5;   % Passenger operating cost per lap
Cc = 2;     % Cargo operating cost per lap





% 2. Income

Income = (n_patitos * (Ip1 + (Ip2 * laps))) + ...
         (n_cargo * (Ic1 + (Ic2 * laps)));

% 3. Cost
Cost = laps * (Ce + (n_patitos * Cp) + (n_cargo * Cc)) * EF;

% 4. Net Income
Net_Income =(int32( Income - Cost));


% =========================================================================
%% --- REPORTE DE PUNTAJE EN CONSOLA ---
% =========================================================================
fprintf('\n==============================================\n');
fprintf('   MISIÓN: %s\n', upper(nombre_mision));
fprintf('==============================================\n');
fprintf(' Vueltas:      %d\n', laps);
fprintf(' Pasajeros:    %d\n', n_patitos);
fprintf(' Cargas:       %d\n', n_cargo);
fprintf('----------------------------------------------\n');
fprintf(' PUNTOS TOTALES: %d\n', Net_Income);
fprintf('==============================================\n\n');
