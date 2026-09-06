clc
clear

% --- Constantes ---
Cd_Banner = 0.003;
Cd_avion = 0.015;
S_avion = 1.3;
ro = 1.225;
distancia_lap = 1277; % x (m)

% --- Rangos de evaluación (Ajustalos según tu necesidad) ---
potencias = 600:20:2000;      % Watts
largos_banner = 1:0.1:6;      % Metros

% Preasignación de matrices
[P_grid, L_grid] = meshgrid(potencias, largos_banner);
Puntaje = zeros(size(P_grid));
Vueltas_Enteras = zeros(size(P_grid)); 

% --- Bucle de evaluación ---
for i = 1:size(L_grid, 1)
    for j = 1:size(L_grid, 2)
        P = P_grid(i,j);
        L = L_grid(i,j);
        
        % 1. Superficie del banner (tu fórmula cuadrática)
        S_B = 1/5 * (L)^2;
        
        % 2. Aerodinámica: Velocidad de equilibrio
        SCd_total = (S_avion * Cd_avion + S_B * Cd_Banner);
        v = ( (2 * P) / (ro * SCd_total) )^(1/3);
        
        % 3. Laps teóricos según restricciones
        % T = 5 min (300s) | Energía = 100Wh (360,000 Joules)
        laps_tiempo = 300 / (distancia_lap / v);
        laps_energia = (100 * 3600 / P) / (distancia_lap / v); 
        
        laps_teoricos = min(laps_tiempo, laps_energia);
        
        % 4. Vueltas válidas (Número Entero)
        vueltas = floor(laps_teoricos);
        
        % 5. Guardar resultados
        Vueltas_Enteras(i,j) = vueltas;
        Puntaje(i,j) = vueltas * L;
    end
end

% --- Visualización ---
figure('Color', 'w', 'Name', 'Análisis de Competencia');

% surf(X, Y, Z, C) -> C es Vueltas_Enteras para el color
surf(L_grid, P_grid, Puntaje, Vueltas_Enteras);

% Estética y Color
shading interp; % Para que no se vean las líneas de la malla y el color sea fluido
colormap(jet);  % Mapa de colores: Azul (pocas vueltas) -> Rojo (muchas vueltas)
h = colorbar;
ylabel(h, 'Vueltas Completadas (Enteros)');

% Etiquetas
xlabel('Largo del Banner (m)');
ylabel('Potencia (W)');
zlabel('Puntaje Total (Vueltas * Largo)');
title('Mapa de Puntaje: Altura = Puntos | Color = Vueltas');

grid on;
view(135, 30); % Ángulo de visión para apreciar los escalones

% --- Mostrar el "Sweet Spot" ---
[max_val, idx] = max(Puntaje(:));
fprintf('--- CONFIGURACIÓN ÓPTIMA ENCONTRADA ---\n');
fprintf('Puntaje Máximo: %.2f\n', max_val);
fprintf('Largo de Banner: %.2f m\n', L_grid(idx));
fprintf('Potencia: %.0f W\n', P_grid(idx));
fprintf('Vueltas completas: %d\n', Vueltas_Enteras(idx));