function plot_results(inform, t, Energy, S, plane1, motor1, prop1, MTOW, throttle, t_n)
% plot_results: Genera gráficos y un resumen de la simulación de vuelo.
% VERSIÓN 5.0:
% - Reorganizado en 3 Figuras separadas para claridad.
% - Figura 1: Trayectoria 3D
% - Figura 2: 5 Gráficos de Series de Tiempo
% - Figura 3: Diagrama de Vectores 3D

g = 9.81; % Constante gravitacional
tiempo = inform(10,:); % Vector de tiempo para todos los gráficos
colormap_to_use = jet; % Mapa de colores

% =========================================================================
% --- FIGURA 1: TRAYECTORIA 3D ---
% =========================================================================
figure; % Abre la Figura 1
colormap(colormap_to_use); 
scatter3(inform(1,:), inform(2,:), inform(3,:), 36, tiempo, 'filled');
title('Gráfico de Dispersión 3D (Color por Tiempo)');
xlabel('Eje X (m)');
ylabel('Eje Y (m)');
zlabel('Eje Z (m)');
grid on;
axis equal; % Usa 'axis equal' para una mejor proporción 3D
colorbar; 
sgtitle('Análisis de Vuelo: Trayectoria 3D', 'FontSize', 14, 'FontWeight', 'bold');

% =========================================================================
% --- FIGURA 2: GRÁFICOS DE SERIES DE TIEMPO ---
% =========================================================================
figure; % Abre la Figura 2
colormap(colormap_to_use); 
num_plots = 5; % 5 gráficos en esta figura

% --- 1. Velocidad vs. Tiempo ---
subplot(num_plots, 1, 1);
norma_vector_nuevo = sqrt(inform(4,:).^2 + inform(5,:).^2 + inform(6,:).^2);
scatter(tiempo, norma_vector_nuevo, 36, tiempo, 'filled');
hold on;
plot(tiempo, norma_vector_nuevo, 'k-', 'LineWidth', 0.5); 
hold off;
title('Velocidad vs. Tiempo');
xlabel('Tiempo (s)');
ylabel('Velocidad (m/s)');
grid on;
ylim_vel = [min(norma_vector_nuevo)*0.9, max(norma_vector_nuevo)*1.1];
if ylim_vel(1) > 0 && ylim_vel(2) < 30; ylim_vel = [0, 30]; end % Límite default
ylim(ylim_vel);
colorbar;

% --- 2. Cl vs. Tiempo ---
subplot(num_plots, 1, 2);
scatter(tiempo, inform(11,:), 36, tiempo, 'filled');
hold on;
plot(tiempo, inform(11,:), 'k-', 'LineWidth', 0.5);
hold off;
title('Cl vs. Tiempo');
xlabel('Tiempo (s)');
ylabel('Cl');
grid on;
ylim_cl = [min(inform(11,:))*0.9, max(inform(11,:))*1.1];
if ylim_cl(1) > 0 && ylim_cl(2) < 0.8; ylim_cl = [0, 0.8]; end % Límite default
ylim(ylim_cl);
colorbar;

% --- 3. Cl/Cd vs. Tiempo ---
subplot(num_plots, 1, 3); 
eficiencia = inform(11,:)./inform(12,:); % Fila 11 (cl) / Fila 12 (cd_total)
scatter(tiempo, eficiencia, 36, tiempo, 'filled');
hold on;
plot(tiempo, eficiencia, 'k-', 'LineWidth', 0.5);
hold off;
title('Eficiencia (Cl/Cd) vs. Tiempo');
xlabel('Tiempo (s)');
ylabel('Cl/Cd');
grid on;
ylim_eff = [min(eficiencia)*0.9, max(eficiencia)*1.1];
if ylim_eff(1) > 0 && ylim_eff(2) < 20; ylim_eff = [0, 20]; end % Límite default
ylim(ylim_eff);
colorbar;

% --- 4. Cd (Total) vs. Tiempo ---
subplot(num_plots, 1, 4); 
cd_total_vec = inform(12,:); % Fila 12
scatter(tiempo, cd_total_vec, 36, tiempo, 'filled');
hold on;
plot(tiempo, cd_total_vec, 'k-', 'LineWidth', 0.5);
hold off;
title('Cd (Total) vs. Tiempo');
xlabel('Tiempo (s)');
ylabel('Cd');
grid on;
ylim_cd = [min(inform(12,:))*0.9, max(inform(12,:))*1.1];
if ylim_cd(1) > 0 && ylim_cd(2) < 0.1; ylim_cd = [0, 0.1]; end % Límite default
ylim(ylim_cd); 
colorbar;

% --- 5. Thrust vs. Drag ---
subplot(num_plots, 1, 5); 
drag_N = inform(13,:);
thrust_N = inform(14,:);
scatter(tiempo, drag_N, 36, tiempo, 'filled');
hold on;
plot(tiempo, thrust_N, 'r-', 'LineWidth', 2);
hold off;
title('Fuerzas: Thrust (Rojo) vs. Drag (Color) vs. Tiempo');
xlabel('Tiempo (s)');
ylabel('Fuerza (N)');
grid on;
legend('Drag', 'Thrust', 'Location', 'best');
ylim_force_max = max([max(drag_N), max(thrust_N)]) * 1.1;
ylim_force_min = min(0, min(drag_N)*0.9);
ylim([ylim_force_min, ylim_force_max]);
colorbar;

% --- Título General para la Figura 2 ---
sgtitle('Análisis de Vuelo: Series de Tiempo', 'FontSize', 14, 'FontWeight', 'bold');

% =========================================================================
% --- FIGURA 3: DIAGRAMA DE VECTORES DE FUERZA 3D ---
% =========================================================================
figure; % Abre la TERCERA ventana de figura
hold on;
grid on;
axis equal;
title('Vectores de Fuerza (cada 3 seg)');
xlabel('Eje X (m)');
ylabel('Eje Y (m)');
zlabel('Eje Z (m)');
view(3); % Vista 3D

% --- Trazar trayectoria como PUNTOS GRISES semitransparentes ---
scatter3(inform(1,:), inform(2,:), inform(3,:), ...
    10, [0.6 0.6 0.6], 'filled', 'MarkerFaceAlpha', 0.3); 

% Definimos cada cuántos pasos dibujar un vector
plot_interval_time = 3; % Cada 3 segundos
plot_interval_steps = round(plot_interval_time / t_n); 
if plot_interval_steps < 1; plot_interval_steps = 1; end % Safeguard
indices_to_plot = 1:plot_interval_steps:length(tiempo);

% Factor de escala para que los vectores sean visibles
scale_factor = 15 / (MTOW * g); % Mantenemos la escala grande

for i = indices_to_plot
    % Posición
    pos = inform(1:3, i);
    
    % Vectores (filas 15 a 23)
    LIFT_vec   = inform(15:17, i) * scale_factor;
    THRUST_vec = inform(18:20, i) * scale_factor;
    DRAG_vec   = inform(21:23, i) * scale_factor;
    WEIGHT_vec = [0; 0; -MTOW*g] * scale_factor;
    
    % Dibujar los vectores
    quiver3(pos(1), pos(2), pos(3), LIFT_vec(1),   LIFT_vec(2),   LIFT_vec(3), 'b', 'LineWidth', 2);
    quiver3(pos(1), pos(2), pos(3), THRUST_vec(1), THRUST_vec(2), THRUST_vec(3), 'r', 'LineWidth', 2);
    quiver3(pos(1), pos(2), pos(3), DRAG_vec(1),   DRAG_vec(2),   DRAG_vec(3), 'g', 'LineWidth', 2);
    quiver3(pos(1), pos(2), pos(3), WEIGHT_vec(1), WEIGHT_vec(2), WEIGHT_vec(3), 'k', 'LineWidth', 2);
end
legend('Trayectoria', 'Lift', 'Thrust', 'Drag', 'Weight', 'Location', 'best');
hold off;
sgtitle('Análisis de Vuelo: Diagrama de Vectores 3D', 'FontSize', 14, 'FontWeight', 'bold');
    
    
% =========================================================================
% --- Resumen en Consola ---
% =========================================================================
tiempo_total_s = t;
tiempo_total_min = t/60;
consumo_Ah = Energy;
consumo_Wh = Energy*3.7*S;
maxCL=max(inform(11,:)); 
fprintf("\n==== RESULTADOS DE LA SIMULACIÓN ====\n");
fprintf('Avion: %s\n', plane1);
fprintf('Motor: %s\n', motor1);
fprintf('Helice: %s\n', prop1);
fprintf('MTOW: %.2f kg\n', MTOW);
fprintf('Throttle: %.2f us\n', throttle);
fprintf("⏱ Tiempo total (vuelta): %.2f s (%.2f min)\n", tiempo_total_s, tiempo_total_min);
fprintf("🔋 Consumo(vuelta): %.4f Ah\n", consumo_Ah);
fprintf("🔋 Consumo(vuelta): %.4f Wh\n", consumo_Wh);
fprintf("📈 Max CL alcanzado: %.3f\n", maxCL);
end

