package ejemplo;

public class Ejemplo {

    // Constantes long y double: fuerzan slots dobles en el constant pool.
    public static final long UN_LONG = 1234567890123L;
    public static final double UN_DOUBLE = 3.14159265358979;

    private final String canario = "canario-en-el-pool";

    // Nombre cualificado, deliberadamente SIN import: un escaner de imports
    // no lo veria; el constant pool si.
    public java.util.List<String> construir() {
        java.util.ArrayList<String> lista = new java.util.ArrayList<>();
        lista.add(canario);
        return lista;
    }
}
