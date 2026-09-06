function [T_or_F, filaInterp] = avion_cl(data_in, cl_query)
    % v4.0: Interpolación Parabólica Robusta
    if ischar(data_in) || isstring(data_in)
        raw_text = fileread(data_in);
        data_matrix = sscanf(raw_text, '%f %f', [2, inf]);
        data_matrix = data_matrix.'; 
        T = table(data_matrix(:,1), data_matrix(:,2), 'VariableNames', {'cl', 'cd'});
        T = sortrows(T, "cl");
        [unique_cl, ~, idx] = unique(T.cl);
        cd_mean = accumarray(idx, T.cd, [], @mean);
        T = table(unique_cl, cd_mean, 'VariableNames', {'cl', 'cd'});
        T_or_F = T; 
    else
        T = data_in;
        T_or_F = T;
    end
    
    filaInterp = struct('cl', 0, 'c_d', 0); % Inicialización para evitar el error de indexing
    
    if nargin > 1 && ~isempty(cl_query)
        % --- AJUSTE PARABÓLICO AERODINÁMICO ---
        % Cd = p1*Cl^2 + p2*Cl + p3
        coeffs = polyfit(T.cl, T.cd, 2);
        
        % Calculamos el Cd con la parábola
        cd_fit = polyval(coeffs, cl_query);
        
        % SEGURIDAD: El Cd no puede ser menor al mínimo medido (piso físico)
        cd_min_medido = min(T.cd);
        filaInterp.c_d = max(cd_fit, cd_min_medido);
        filaInterp.cl = cl_query;
    end

end