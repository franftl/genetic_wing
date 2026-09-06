function T = prop(filename)
    % PROP Lee archivo de datos de hélice (formato APC), convierte a MKS y devuelve tabla
    % v2.5: Optimización de rendimiento: Lee el archivo completo a memoria (fileread) 
    %       y procesa el string, eliminando fgetl/feof.
    
    % Factores de conversión
    mph2ms = 0.44704;      % 1 mph = 0.44704 m/s
    hp2w   = 745.7;        % 1 hp = 745.7 W
    inlbf2Nm = 0.1130;     % 1 in-lbf = 0.1130 N·m
    lbf2N  = 4.4482;       % 1 lbf = 4.448a2 N
    
    % --- Paso 1: Leer archivo completo a memoria ---
    try
        raw_text = fileread(filename);
    catch ME
        error('No se pudo leer el archivo %s. Error: %s', filename, ME.message);
    end
    
    % Dividir en líneas
    lines = strsplit(raw_text, {'\r\n', '\r', '\n'}, 'CollapseDelimiters', false);
    num_lines = numel(lines);
    
    % --- Paso 2: Primera pasada para CONTAR ---
    data_line_count = 0;
    current_rpm_count = NaN;
    
    for i = 1:num_lines
        line = strtrim(lines{i});
        if isempty(line)
            continue;
        end
        
        % Detectar línea con PROP RPM (Optimizado)
        if startsWith(line, 'PROP RPM')
            rpm_token = sscanf(line, 'PROP RPM = %d');
            if ~isempty(rpm_token)
                current_rpm_count = rpm_token;
            end
            continue
        end
        
        % Intentar leer línea numérica (Optimizado con sscanf)
        nums = sscanf(line, '%f'); 
        
        if ~isempty(nums) && ~isnan(current_rpm_count)
            if numel(nums) == 15
                data_line_count = data_line_count + 1;
            end
        end
    end
    
    if data_line_count == 0
        error('No se pudieron leer datos numéricos del archivo de hélice: %s. ¿Formato correcto?', filename);
    end
    
    % --- Paso 3: Pre-alocar memoria ---
    data = zeros(data_line_count, 15);
    rpm_val = zeros(data_line_count, 1);
    
    % --- Paso 4: Segunda pasada para LLENAR ---
    idx = 1;
    current_rpm_fill = NaN;
    
    for i = 1:num_lines
        line = strtrim(lines{i});
        if isempty(line)
            continue;
        end
        
        % Detectar línea con PROP RPM (Optimizado)
        if startsWith(line, 'PROP RPM')
            rpm_token = sscanf(line, 'PROP RPM = %d');
            if ~isempty(rpm_token)
                current_rpm_fill = rpm_token;
            end
            continue
        end
        
        % Intentar leer línea numérica (Optimizado con sscanf)
        nums = sscanf(line, '%f');
        
        if ~isempty(nums) && ~isnan(current_rpm_fill)
            if numel(nums) == 15
                % sscanf devuelve un vector columna, lo trasponemos (.')
                data(idx, :) = nums.'; 
                rpm_val(idx) = current_rpm_fill;
                idx = idx + 1;
                
                % Pequeña optimización: si ya llenamos todo, salimos
                if idx > data_line_count
                    break;
                end
            end
        end
    end

    % --- Paso 5: Conversión y Creación de Tabla ---
    
    % Conversión a MKS
    data(:,1)  = data(:,1)  * mph2ms;   % V [m/s]
    data(:,6)  = data(:,6)  * hp2w;     % PWR_hp → W
    data(:,7)  = data(:,7)  * inlbf2Nm; % Torque_inlbf → N·m
    data(:,8)  = data(:,8)  * lbf2N;    % Thrust_lbf → N
    
    % Nombres de columnas en MKS
    varNames = {'V_ms','J','Pe','Ct','Cp','PWR_W_fromHP','Torque_Nm_fromInlbf','Thrust_N_fromLbf',...
                'PWR_W','Torque_Nm','Thrust_N_fromFile','Thrust_per_W','Mach','Reyn','FOM'};
    
    % Crear tabla


    % --- FIX: Crear la tabla final para interpProp ---
    % interpProp (en Canvas) espera 'Thrust_N' y 'Power_W'
    % Usamos los valores convertidos a MKS (de Lbf y HP).
    
% --- DENTRO DE prop.m ---
T_raw = array2table(data, 'VariableNames', varNames);
T_raw.RPM = rpm_val;

% --- BUSCA ESTO EN TU FUNCIÓN prop.m ---
T_final = T_raw(:, {'RPM', 'V_ms', 'Ct', 'Cp'});
T_final.Thrust_N = T_raw.Thrust_N_fromLbf; 
T_final.Power_W = T_raw.PWR_W_fromHP;   

% --- AGREGA ESTA LÍNEA JUSTO AQUÍ ---
T_final.Torque_Nm = T_raw.Torque_Nm_fromInlbf; % <--- ESTO FALTA

% Reasignamos la salida
T = T_final;
end

