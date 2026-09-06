function [T, filaInterp] = motor(data_in, throttle_query)
% motor: Lee un archivo .dat de motor O una tabla ya cargada.
% Devuelve la tabla (T) y, si se pide, una fila interpolada.
%
% v2.0: Modificado para aceptar un nombre de archivo (string) O
%       una tabla (table) como primer argumento.
    
    % --- Bloque 1: Cargar/Asignar la tabla T ---
    if ischar(data_in) || isstring(data_in)
        % Opción A: data_in es un nombre de archivo, lo leemos.
        filename = data_in;
        try
            opts = detectImportOptions(filename, 'FileType','text');
            opts = setvartype(opts, 'double'); % todas las columnas como números
            T = readtable(filename, opts);
        catch e
            error('Error al leer el archivo de motor %s: %s', filename, e.message);
        end
        
    elseif istable(data_in)
        % Opción B: data_in ya es una tabla, solo la asignamos.
        T = data_in;
    else
        error('La entrada de "motor" debe ser un nombre de archivo (string) o una tabla (table).');
    end
    
    % --- Bloque 2: Interpolación (Opcional) ---
    filaInterp = [];
    
    % Si se pide interpolación
    if nargin > 1
        campos = T.Properties.VariableNames; % nombres de columnas
        filaInterp = struct();
        
        % Interpolar todas las columnas excepto ESC_throttle
        for i = 2:numel(campos)
            campo = campos{i};
            try
                filaInterp.(campo) = interp1(T.ESC_throttle, T.(campo), throttle_query, 'linear');
            catch e
                warning('Error interpolando campo de motor: %s. %s', campo, e.message);
                filaInterp.(campo) = NaN;
            end
        end
        
        % Agregar el valor de throttle consultado
        filaInterp.ESC_throttle = throttle_query;
    end
end

