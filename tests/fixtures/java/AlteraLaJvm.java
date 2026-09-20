package ejemplo;

/**
 * Sonda de R-A05: altera la configuracion GLOBAL de la JVM sin tocar
 * `System.setProperty`, que es lo unico que la regla reconocia hasta el
 * 21-sep-2026.
 *
 * <p>Las dos llamadas cambian el `Locale` y la zona horaria por defecto de
 * TODA la JVM, o sea de todos los plug-ins que comparten ese servidor Appian.
 * Es exactamente lo que la politica de AppMarket prohibe con su
 * «using System.setProperty() or any other method», y medido en su dia pasaba
 * las diez reglas R-A con cero hallazgos.
 *
 * <p>No referencia `java.lang.System` a proposito: esa referencia era la mitad
 * de la heuristica vieja, y sin ella la regla ni se planteaba disparar.
 */
public class AlteraLaJvm {

    public void alterarLaJvmGlobal() {
        java.util.Locale.setDefault(java.util.Locale.US);
        java.util.TimeZone.setDefault(java.util.TimeZone.getTimeZone("UTC"));
    }
}
