function fila = interpProp(T, V_query, RPM_query)
% INTERP_PROP Interpola una tabla de hélice en velocidad y RPM
% T: tabla original (la tabla cargada por prop.m)
% V_query: velocidad en m/s
% RPM_query: RPM deseada
%
% Devuelve: una 'fila' (struct) con todos los campos interpolados

    % Campos que queremos interpolar
    campos = T.Properties.VariableNames;
    % Excluimos las columnas que son 'indices'
    campos = campos(~strcmp(campos, 'RPM') & ~strcmp(campos, 'V_ms')); 
    
    % Inicializamos la estructura de salida
    fila = struct();
    for k = 1:length(campos)
        fila.(campos{k}) = NaN;
    end
    fila.V_ms = V_query;
    fila.RPM  = RPM_query; % Devolvemos el RPM solicitado por defecto

    % Extraemos valores únicos de RPM de la tabla
    RPMs = unique(T.RPM);
    
    % --- Paso 1: Interpolamos en Velocidad (V_ms) para cada RPM ---
    
    % Creamos una matriz temporal para guardar los valores
    % (filas = cada RPM, columnas = cada campo como Ct, Cp, etc.)
    interp_vals_en_V = nan(length(RPMs), length(campos));
    
    for i = 1:length(RPMs)
        % Obtenemos los datos solo para este RPM
        idx = (T.RPM == RPMs(i));
        
        % Aseguramos que haya al menos 2 puntos para interpolar en V
        if sum(idx) >= 2
            for j = 1:length(campos)
                % Interpolamos este campo (ej. 'Thrust_N') a lo largo de V_ms
                % para encontrar el valor en V_query.
                % Usamos 'extrap' por si V_query está un poco fuera de rango.
                interp_vals_en_V(i,j) = interp1(T.V_ms(idx), T{idx, campos{j}}, V_query, 'linear', 'extrap');
            end
        elseif sum(idx) == 1
            % Si solo hay un punto de V, usamos ese valor
             for j = 1:length(campos)
                interp_vals_en_V(i,j) = T{idx, campos{j}};
             end
        end
    end
    
    % --- Paso 2: Interpolamos en RPM ---
    
    % FIX: Añadimos un 'safeguard' para el error "requires at least two sample points".
    
    if length(RPMs) < 2
        % --- Caso A: Solo hay 0 o 1 RPM en los datos ---
        % No podemos interpolar entre RPMs.
        
        if length(RPMs) == 1
            % Si hay 1 RPM, devolvemos los valores ya interpolados en V (Paso 1).
            for j = 1:length(campos)
                fila.(campos{j}) = interp_vals_en_V(1, j);
            end
            fila.RPM = RPMs(1); % Devolvemos el único RPM que encontramos
        else
            % Si hay 0 RPMs, 'fila' ya es NaN, lo cual es correcto.
            % No hacemos nada.
        end
        
    else
        % --- Caso B: Hay 2 o más RPMs (Caso normal) ---
        
        % Aseguramos que RPM_query esté dentro del rango de la hélice
        RPM_query_clamped = max(min(RPM_query, max(RPMs)), min(RPMs));
        
        for j = 1:length(campos)
            % Interpolamos la columna (ej. 'Thrust_N' en V_query) a lo largo
            % de las RPMs para encontrar el valor en RPM_query.
            fila.(campos{j}) = interp1(RPMs, interp_vals_en_V(:,j), RPM_query_clamped, 'linear', 'extrap');
        end
        
        % Actualizamos el RPM al valor 'clamped' (limitado)
        fila.RPM = RPM_query_clamped;
    end
    
end

