# Cómo correr esto desde Visual Studio Code

Esta carpeta (`UAV FP`) ya tiene todo lo que hace falta: el paquete `optimizacion_ala/`, el notebook `01_Optimizacion_Ala.ipynb`, `requirements.txt`, y una carpeta `.vscode/` con las extensiones recomendadas precargadas.

## 1. Instalar lo necesario (una sola vez)

1. Instalá [Visual Studio Code](https://code.visualstudio.com/) si no lo tenés.
2. Instalá [Python 3.10+](https://www.python.org/downloads/) (marcá "Add python.exe to PATH" en el instalador de Windows).
3. Abrí la carpeta `UAV FP` completa en VS Code: `File > Open Folder...` y seleccioná `Documents\Claude\Projects\ITBA 2026 1C\Proyecto Final\UAV FP`.
4. VS Code va a sugerir instalar las extensiones **Python** y **Jupyter** (aparece un aviso abajo a la derecha) -- aceptá. Si no aparece el aviso, instalalas a mano desde el ícono de Extensiones (`Ctrl+Shift+X`): buscá "Python" (de Microsoft) y "Jupyter" (de Microsoft).

## 2. Crear el entorno virtual e instalar dependencias (una sola vez)

Abrí una terminal dentro de VS Code (`Terminal > New Terminal`, o `` Ctrl+` ``) y corré:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

(En Mac/Linux el segundo comando es `source .venv/bin/activate` en vez de `.venv\Scripts\activate`.)

Esto crea una carpeta `.venv` con un Python aislado para este proyecto, y le instala AeroSandbox, Jupyter, pandas, matplotlib, etc. La instalación de AeroSandbox puede tardar unos minutos la primera vez.

## 3. Correr el notebook

1. Abrí `01_Optimizacion_Ala.ipynb` (doble clic en el panel de archivos de la izquierda).
2. Arriba a la derecha del notebook, hacé clic en "Select Kernel" (o el nombre de kernel que aparezca) y elegí el intérprete `.venv` que acabás de crear -- debería aparecer como algo como `Python 3.x.x ('.venv': venv)`.
3. Corré las celdas en orden con el botón de play de cada celda, o `Run All` arriba. La celda de "Correr una generación" (sección 3) está pensada para correrla muchas veces seguidas -- cada vez que la corrés avanza una generación más.

No hace falta ni `claude login` ni ninguna `API_KEY`: el backend activo (`optimizacion_ala/ga_numerico.py`) no llama a ningún modelo de IA, corre todo localmente.

## 4. Si algo no anda

- **"python no se reconoce como comando"**: reinstalá Python marcando la casilla de agregarlo al PATH, o usá la ruta completa al ejecutable.
- **El kernel del notebook no aparece / dice "kernel not found"**: `Ctrl+Shift+P` > "Python: Select Interpreter" > elegí el de `.venv`, después reintentá "Select Kernel" en el notebook.
- **Falla la instalación de AeroSandbox**: asegurate de tener el entorno virtual activado (el prompt de la terminal debería mostrar `(.venv)` al principio) antes de correr `pip install`.
