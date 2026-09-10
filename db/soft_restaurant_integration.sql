-- ==============================================================================
-- RESTAURANTE RYU - INTEGRACIÓN SOFT RESTAURANT (SQL SERVER)
-- Inyección de Comandas IA, Descuento Automático de Inventario y Auditoría
-- Compatible con: Soft Restaurant 9.5 / 10 / 11 / Enterprise (MS SQL Server)
-- ==============================================================================

USE [SOFTRESTAURANT10]; -- Modificar según el nombre de la base de datos de producción
GO

-- 1. Tabla de Registro de Comandas IA (Auditoría y Trazabilidad)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ryu_pedidos_ia')
BEGIN
    CREATE TABLE ryu_pedidos_ia (
        id_pedido_ia INT IDENTITY(1,1) PRIMARY KEY,
        folio_ryu VARCHAR(50) NOT NULL UNIQUE,
        id_cheque_soft INT NULL,
        cliente_nombre VARCHAR(120) NOT NULL,
        cliente_telefono VARCHAR(30) NOT NULL,
        tipo_entrega VARCHAR(30) NOT NULL, -- 'DOMICILIO' o 'SUCURSAL'
        direccion_entrega VARCHAR(250) NULL,
        zona_entrega VARCHAR(80) NULL,
        subtotal_platillos DECIMAL(10,2) NOT NULL,
        costo_envio DECIMAL(10,2) DEFAULT 0.00,
        total_a_cobrar DECIMAL(10,2) NOT NULL,
        metodo_pago VARCHAR(50) DEFAULT 'EFECTIVO',
        monto_paga_con DECIMAL(10,2) DEFAULT 0.00,
        cambio_devuelto DECIMAL(10,2) DEFAULT 0.00,
        es_pedido_futuro BIT DEFAULT 0,
        fecha_hora_programada VARCHAR(100) NULL,
        estado VARCHAR(30) DEFAULT 'PENDIENTE_COCINA',
        inventario_descontado BIT DEFAULT 0,
        fecha_creacion DATETIME DEFAULT GETDATE(),
        origen VARCHAR(50) DEFAULT 'IA_TELEFONIA_RYU'
    );
    PRINT 'Tabla ryu_pedidos_ia creada exitosamente.';
END
GO

-- 2. Tabla de Detalle de Partidas de la Comanda IA
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ryu_pedidos_ia_detalle')
BEGIN
    CREATE TABLE ryu_pedidos_ia_detalle (
        id_detalle INT IDENTITY(1,1) PRIMARY KEY,
        folio_ryu VARCHAR(50) NOT NULL,
        id_producto_soft VARCHAR(50) NULL,
        nombre_platillo VARCHAR(150) NOT NULL,
        cantidad INT NOT NULL DEFAULT 1,
        precio_unitario DECIMAL(10,2) NOT NULL,
        subtotal DECIMAL(10,2) NOT NULL,
        estacion_cocina VARCHAR(50) DEFAULT 'hot_kitchen',
        notas_especiales VARCHAR(250) NULL,
        inventario_descontado BIT DEFAULT 0,
        FOREIGN KEY (folio_ryu) REFERENCES ryu_pedidos_ia(folio_ryu) ON DELETE CASCADE
    );
    PRINT 'Tabla ryu_pedidos_ia_detalle creada exitosamente.';
END
GO

-- 3. Stored Procedure: Registrar Pedido IA y Descontar Inventario
IF OBJECT_ID('sp_Ryu_RegistrarPedidoIA', 'P') IS NOT NULL
    DROP PROCEDURE sp_Ryu_RegistrarPedidoIA;
GO

CREATE PROCEDURE sp_Ryu_RegistrarPedidoIA
    @FolioRyu VARCHAR(50),
    @ClienteNombre VARCHAR(120),
    @ClienteTelefono VARCHAR(30),
    @TipoEntrega VARCHAR(30),
    @DireccionEntrega VARCHAR(250),
    @ZonaEntrega VARCHAR(80),
    @SubtotalPlatillos DECIMAL(10,2),
    @CostoEnvio DECIMAL(10,2),
    @TotalACobrar DECIMAL(10,2),
    @MetodoPago VARCHAR(50),
    @PagaCon DECIMAL(10,2),
    @EsFuturo BIT,
    @FechaProgramada VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        -- 3.1 Registrar encabezado en ryu_pedidos_ia
        DECLARE @Cambio DECIMAL(10,2) = 0.00;
        IF @PagaCon > @TotalACobrar
            SET @Cambio = @PagaCon - @TotalACobrar;

        IF EXISTS (SELECT 1 FROM ryu_pedidos_ia WHERE folio_ryu = @FolioRyu)
        BEGIN
            UPDATE ryu_pedidos_ia
            SET cliente_nombre = @ClienteNombre,
                cliente_telefono = @ClienteTelefono,
                total_a_cobrar = @TotalACobrar,
                direccion_entrega = @DireccionEntrega
            WHERE folio_ryu = @FolioRyu;
        END
        ELSE
        BEGIN
            INSERT INTO ryu_pedidos_ia (
                folio_ryu, cliente_nombre, cliente_telefono, tipo_entrega,
                direccion_entrega, zona_entrega, subtotal_platillos, costo_envio,
                total_a_cobrar, metodo_pago, monto_paga_con, cambio_devuelto,
                es_pedido_futuro, fecha_hora_programada, estado, inventario_descontado
            )
            VALUES (
                @FolioRyu, @ClienteNombre, @ClienteTelefono, @TipoEntrega,
                @DireccionEntrega, @ZonaEntrega, @SubtotalPlatillos, @CostoEnvio,
                @TotalACobrar, @MetodoPago, @PagaCon, @Cambio,
                @EsFuturo, @FechaProgramada, 'PENDIENTE_COCINA', 0
            );
        END

        -- 3.2 Opcional: Si existe la tabla nativa de 'cheques' de Soft Restaurant, insertar cuenta
        IF EXISTS (SELECT * FROM sys.tables WHERE name = 'cheques')
        BEGIN
            -- Comprobar si ya existe el cheque con mesa 'DOMICILIO-IA' o folio
            IF NOT EXISTS (SELECT 1 FROM cheques WHERE descripcion = @FolioRyu)
            BEGIN
                -- Inserción en la estructura estándar de cheques de Soft Restaurant
                INSERT INTO cheques (
                    fecha, horapertura, mesa, mesero, personas,
                    total, pagado, estado, descripcion
                )
                VALUES (
                    CAST(GETDATE() AS DATE), CONVERT(VARCHAR(8), GETDATE(), 108),
                    CASE WHEN @TipoEntrega = 'domicilio' THEN 'DOMICILIO-IA' ELSE 'RECOGER-IA' END,
                    'IA_RYU', 1, @TotalACobrar, 0.00, 'A', @FolioRyu
                );

                DECLARE @NuevoChequeId INT = SCOPE_IDENTITY();
                UPDATE ryu_pedidos_ia SET id_cheque_soft = @NuevoChequeId WHERE folio_ryu = @FolioRyu;
            END
        END

        COMMIT TRANSACTION;
        SELECT 1 AS Exito, 'Pedido registrado exitosamente en Soft Restaurant' AS Mensaje;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        SELECT 0 AS Exito, ERROR_MESSAGE() AS Mensaje;
    END CATCH
END
GO

-- 4. Stored Procedure: Descontar Inventario por Platillo / Insumos
IF OBJECT_ID('sp_Ryu_DescontarInventarioItem', 'P') IS NOT NULL
    DROP PROCEDURE sp_Ryu_DescontarInventarioItem;
GO

CREATE PROCEDURE sp_Ryu_DescontarInventarioItem
    @FolioRyu VARCHAR(50),
    @NombrePlatillo VARCHAR(150),
    @Cantidad INT,
    @PrecioUnitario DECIMAL(10,2),
    @Estacion VARCHAR(50),
    @Notas VARCHAR(250)
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        -- 4.1 Registrar partida en el detalle de la comanda IA
        DECLARE @Subtotal DECIMAL(10,2) = @Cantidad * @PrecioUnitario;
        
        INSERT INTO ryu_pedidos_ia_detalle (
            folio_ryu, nombre_platillo, cantidad, precio_unitario, subtotal,
            estacion_cocina, notas_especiales, inventario_descontado
        )
        VALUES (
            @FolioRyu, @NombrePlatillo, @Cantidad, @PrecioUnitario, @Subtotal,
            @Estacion, @Notas, 1
        );

        -- 4.2 Descuento directo en la tabla de existencias de Soft Restaurant (si existe)
        -- Caso A: Tabla 'existencias' nativa de Soft Restaurant
        IF EXISTS (SELECT * FROM sys.tables WHERE name = 'existencias')
        BEGIN
            UPDATE existencias
            SET existencia = existencia - @Cantidad
            WHERE idproducto IN (
                SELECT idproducto FROM productos WHERE descripcion LIKE '%' + @NombrePlatillo + '%'
            );
        END

        -- Caso B: Tabla 'inventario' nativa de Soft Restaurant
        IF EXISTS (SELECT * FROM sys.tables WHERE name = 'inventario')
        BEGIN
            UPDATE inventario
            SET stock_actual = stock_actual - @Cantidad
            WHERE descripcion LIKE '%' + @NombrePlatillo + '%';
        END

        -- 4.3 Registrar movimiento en el Kardex (si existe la tabla)
        IF EXISTS (SELECT * FROM sys.tables WHERE name = 'kardex')
        BEGIN
            INSERT INTO kardex (
                fecha, tipo_movimiento, cantidad, referencia, concepto
            )
            VALUES (
                GETDATE(), 'S', @Cantidad, @FolioRyu, 'VENTA COMANDA IA RYU TELEFONIA'
            );
        END

        -- 4.4 Marcar comanda con inventario descontado
        UPDATE ryu_pedidos_ia SET inventario_descontado = 1 WHERE folio_ryu = @FolioRyu;

        COMMIT TRANSACTION;
        SELECT 1 AS Exito, 'Partida registrada e inventario descontado' AS Mensaje;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        SELECT 0 AS Exito, ERROR_MESSAGE() AS Mensaje;
    END CATCH
END
GO

PRINT '======================================================================';
PRINT 'Scripts de Integración Soft Restaurant para Restaurante Ryu instalados.';
PRINT '======================================================================';
