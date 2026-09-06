function plot_results_report(inform, t, Energy, S, plane1, motor1, prop1, MTOW, throttle, t_n)
% plot_results: Generates plots and a summary of the flight simulation.
g = 9.81; 
tiempo = inform(10,:); 

% --- Paleta de Colores ---
dark_blue = [0.00, 0.15, 0.45]; 
light_blue = [0.85, 0.90, 0.95]; 
red_force = [0.75, 0.15, 0.15]; 

% --- FIGURE 1: 3D TRAJECTORY (DEDICATED) ---

% =========================================================================

figure('Name', '3D Trajectory', 'Color', 'w', 'Position', [100, 100, 800, 600]);

hold on;

% Draw the trajectory line

plot3(inform(1,:), inform(2,:), inform(3,:), 'Color', dark_blue, 'LineWidth', 2.5);

% Mark the start and end of the flight

scatter3(inform(1,1), inform(2,1), inform(3,1), 80, 'o', 'MarkerEdgeColor', dark_blue, 'MarkerFaceColor', 'g');

scatter3(inform(1,end), inform(2,end), inform(3,end), 80, 's', 'MarkerEdgeColor', dark_blue, 'MarkerFaceColor', 'r');

title('3D Flight Trajectory', 'FontSize', 14, 'FontWeight', 'bold', 'Color', dark_blue);

xlabel('X Position (m)', 'FontSize', 11, 'FontWeight', 'bold');

ylabel('Y Position (m)', 'FontSize', 11, 'FontWeight', 'bold');

zlabel('Altitude Z (m)', 'FontSize', 11, 'FontWeight', 'bold');

grid on;

set(gca, 'GridAlpha', 0.3, 'FontSize', 11);

axis equal;

view(-45, 30); % Elegant isometric view angle

legend({'Trajectory', 'Start', 'End'}, 'Location', 'best', 'FontSize', 11);

hold off;

% =========================================================================
% --- FIGURE 2: VELOCITY VS TIME (DEDICATED) ---
% =========================================================================
figure('Name', 'Velocity vs Time', 'Color', 'w', 'Position', [150, 150, 800, 400]);
norma_vector_nuevo = sqrt(inform(4,:).^2 + inform(5,:).^2 + inform(6,:).^2);

% --- CÁLCULO DE LÍMITES DINÁMICOS ---
v_min = min(norma_vector_nuevo);
v_max = max(norma_vector_nuevo);
v_range = v_max - v_min;

% Le damos un margen del 10% para que no "toque" los bordes
y_lim_inferior = v_min - 0.1 * v_range;
y_lim_superior = v_max + 0.1 * v_range;

hold on;

% Ajustamos el FILL para que el sombreado baje hasta el límite inferior del eje, no a 0
fill([tiempo, fliplr(tiempo)], [norma_vector_nuevo, ones(1, length(norma_vector_nuevo)) * y_lim_inferior], ...
     light_blue, 'FaceAlpha', 0.6, 'EdgeColor', 'none');

% Main line
plot(tiempo, norma_vector_nuevo, 'Color', dark_blue, 'LineWidth', 2.5);

title('Velocity Profile', 'FontSize', 14, 'FontWeight', 'bold', 'Color', dark_blue);
xlabel('Time (s)', 'FontSize', 11, 'FontWeight', 'bold');
ylabel('Velocity (m/s)', 'FontSize', 11, 'FontWeight', 'bold');

grid on;
set(gca, 'GridAlpha', 0.3, 'FontSize', 11);

% Aplicamos los límites calculados
ylim([y_lim_inferior, y_lim_superior]);
xlim([min(tiempo), max(tiempo)]);

hold off;

% =========================================================================

% =========================================================================
% --- FIGURE 3: AERODYNAMIC ANALYSIS (ACTUALIZADA CON FACTOR DE CARGA) ---
% =========================================================================
figure('Name', 'Aerodynamic Analysis', 'Color', 'w', 'Position', [200, 50, 900, 900]);
num_plots = 6; % Cambiamos a 6 subplots

% 1. Cl vs. Time
subplot(num_plots, 1, 1);
plot(tiempo, inform(11,:), 'Color', dark_blue, 'LineWidth', 2);
title('Lift Coefficient (C_L)', 'FontSize', 11, 'FontWeight', 'bold');
ylabel('C_L'); grid on; xlim([min(tiempo), max(tiempo)]);

% 2. Aerodynamic Efficiency (L/D)
subplot(num_plots, 1, 2); 
eficiencia = inform(11,:)./inform(12,:);
plot(tiempo, eficiencia, 'Color', dark_blue, 'LineWidth', 2);
title('Aerodynamic Efficiency (L/D)', 'FontSize', 11, 'FontWeight', 'bold');
ylabel('L/D'); grid on; xlim([min(tiempo), max(tiempo)]);

% 3. Factor de Carga (n = L/W) <-- NUEVO GRAFICO
subplot(num_plots, 1, 3);
% Calculamos la magnitud del vector sustentación guardado en inform(15:17)
lift_magnitude = sqrt(inform(15,:).^2 + inform(16,:).^2 + inform(17,:).^2);
load_factor = lift_magnitude / (MTOW * g);
plot(tiempo, load_factor, 'Color', [0.5 0, 0.5], 'LineWidth', 2); % Color púrpura
title('Load Factor (n = L/W)', 'FontSize', 11, 'FontWeight', 'bold');
ylabel('n [g]'); grid on; xlim([min(tiempo), max(tiempo)]);
yline(1, '--k', '1g (Nivelado)'); % Línea de referencia en 1g

% 4. Cd (Total) vs. Time
subplot(num_plots, 1, 4); 
plot(tiempo, inform(12,:), 'Color', dark_blue, 'LineWidth', 2);
title('Total Drag Coefficient (C_D)', 'FontSize', 11, 'FontWeight', 'bold');
ylabel('C_D'); grid on; xlim([min(tiempo), max(tiempo)]);

% 5. Thrust vs. Drag
subplot(num_plots, 1, 5); 
drag_N = inform(13,:);
thrust_N = inform(14,:);
hold on;
plot(tiempo, thrust_N, 'Color', red_force, 'LineWidth', 2);
plot(tiempo, drag_N, 'Color', dark_blue, 'LineWidth', 2, 'LineStyle', '--');
title('Longitudinal Force Balance', 'FontSize', 11, 'FontWeight', 'bold');
xlabel('Time (s)'); ylabel('Force (N)'); grid on;
legend({'Thrust', 'Drag'}, 'Location', 'best');
xlim([min(tiempo), max(tiempo)]);

sgtitle('Flight Aerodynamic Analysis', 'FontSize', 14, 'FontWeight', 'bold', 'Color', dark_blue);
% --- DENTRO DE plot_results_report (Figura 3) ---


% ... (otros subplots) ...

% 6. Corriente Instantánea vs. Tiempo
subplot(num_plots, 1, 6);
plot(tiempo, inform(24,:), 'Color', [0.8 0.4 0], 'LineWidth', 2); % Naranja eléctrico
title('Instantaneous Motor Current', 'FontSize', 10, 'FontWeight', 'bold');
ylabel('Current (A)'); grid on; xlim([min(tiempo), max(tiempo)]);


hold off;


% =========================================================================

% --- Console Summary ---

% =========================================================================

tiempo_total_s = t;

tiempo_total_min = t/60;

consumo_Ah = Energy;

consumo_Wh = Energy*3.7*S;

maxCL=max(inform(11,:));

% --- Cálculos de Optimización ---
puntos_eficiencia = 100 / consumo_Wh; 
puntos_velocidad = 5 / tiempo_total_min;
score_combinado = puntos_eficiencia * puntos_velocidad; % Ejemplo de métrica de desempeño

fprintf("\n============================================\n");
fprintf("          AIAA SIMULATION RESULTS           \n");
fprintf("============================================\n");
fprintf(' Aircraft: %s\n', plane1);
fprintf(' Motor:    %s\n', motor1);
fprintf(' Prop:     %s\n', prop1);
fprintf(' MTOW:     %.2f kg\n', MTOW);
fprintf(' Throttle: %.2f us\n', throttle);
fprintf("--------------------------------------------\n");
fprintf(" ⏱ Total Time:    %.2f s (%.2f min)\n", tiempo_total_s, tiempo_total_min);
fprintf(" 🔋 Energy (Ah):   %.4f Ah\n", consumo_Ah);
fprintf(" 🔋 Energy (Wh):   %.4f Wh\n", consumo_Wh);
fprintf(" 📈 Max C_L:       %.3f\n", maxCL);
fprintf("--------------------------------------------\n");
fprintf("      🚀 OPTIMIZATION METRICS (KPIs)        \n");
fprintf("--------------------------------------------\n");
fprintf(" 💡 Pts/Energy (100/Wh): %.4f\n", puntos_eficiencia);
fprintf(" 🏎  Pts/Speed  (5/Time):  %.4f\n", puntos_velocidad);






end