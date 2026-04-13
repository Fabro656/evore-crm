# services/nomina.py — Cálculos de nómina colombiana
from utils import (
    SMLMV_2025, AUXILIO_TRANSPORTE_2025,
    TASA_SALUD_EMP, TASA_PENSION_EMP,
    TASA_SALUD_EMPR, TASA_PENSION_EMPR,
    TASA_CAJA_COMP, TASA_SENA, TASA_ICBF,
    TASA_ARL, TASA_CESANTIAS, TASA_INT_CESANTIAS,
    TASA_PRIMA, TASA_VACACIONES
)
from datetime import date as date_t


class NominaService:

    @staticmethod
    def calcular_nomina(empleado, dias_mes=30, dias_trabajados=None):
        """Retorna dict con todos los calculos de nomina para un empleado.
        Si dias_trabajados < dias_mes, se prorratean salario y aportes."""
        salario_completo = float(empleado.salario_base or 0)
        # Prorrateo si no trabajo el mes completo
        if dias_trabajados is not None and dias_trabajados < dias_mes:
            factor = max(dias_trabajados, 0) / dias_mes
        else:
            factor = 1.0
            dias_trabajados = dias_mes
        salario = round(salario_completo * factor)
        aux_transporte = round(AUXILIO_TRANSPORTE_2025 * factor) if (
            empleado.auxilio_transporte and salario_completo <= 2 * SMLMV_2025
        ) else 0

        deduccion_salud   = round(salario * TASA_SALUD_EMP)
        deduccion_pension = round(salario * TASA_PENSION_EMP)

        fondo_solidaridad = 0
        if salario_completo > 16 * SMLMV_2025:
            fondo_solidaridad = round(salario * 0.012)
        elif salario_completo > 4 * SMLMV_2025:
            fondo_solidaridad = round(salario * 0.01)

        # Retencion en la fuente por renta (Art. 383 ET)
        UVT_2025 = 49799
        retencion_fuente = 0
        if salario_completo > 0:
            # Base gravable: salario - aportes obligatorios (salud+pension)
            base_gravable = salario_completo - deduccion_salud - deduccion_pension
            base_uvt = base_gravable / UVT_2025
            # Tabla retencion (Art. 383 ET simplificada)
            if base_uvt > 360:
                retencion_fuente = round((base_gravable - 360*UVT_2025) * 0.33 + 69.21*UVT_2025)
            elif base_uvt > 150:
                retencion_fuente = round((base_gravable - 150*UVT_2025) * 0.28)
            elif base_uvt > 95:
                retencion_fuente = round((base_gravable - 95*UVT_2025) * 0.19)
            retencion_fuente = round(max(0, retencion_fuente) * factor)

        total_deducciones = deduccion_salud + deduccion_pension + fondo_solidaridad + retencion_fuente
        salario_neto = salario + aux_transporte - total_deducciones

        aporte_salud_empr   = round(salario * TASA_SALUD_EMPR)
        aporte_pension_empr = round(salario * TASA_PENSION_EMPR)
        tasa_arl            = TASA_ARL.get(empleado.nivel_riesgo_arl, TASA_ARL[1])
        aporte_arl          = round(salario * tasa_arl)
        aporte_caja         = round(salario * TASA_CAJA_COMP)
        aporte_sena         = round(salario * TASA_SENA)
        aporte_icbf         = round(salario * TASA_ICBF)
        total_costo_empr    = (salario + aux_transporte + aporte_salud_empr +
                               aporte_pension_empr + aporte_arl + aporte_caja +
                               aporte_sena + aporte_icbf)

        provision_cesantias     = round((salario + aux_transporte) * TASA_CESANTIAS)
        provision_int_cesantias = round(provision_cesantias * TASA_INT_CESANTIAS / 12)
        provision_prima         = round((salario + aux_transporte) * TASA_PRIMA)
        provision_vacaciones    = round(salario * TASA_VACACIONES)
        total_prestaciones      = (provision_cesantias + provision_int_cesantias +
                                   provision_prima + provision_vacaciones)

        return {
            'salario': salario,
            'salario_completo': salario_completo,
            'dias_trabajados': dias_trabajados,
            'dias_mes': dias_mes,
            'factor_prorrateo': round(factor, 4),
            'aux_transporte': aux_transporte,
            'deduccion_salud': deduccion_salud,
            'deduccion_pension': deduccion_pension,
            'fondo_solidaridad': fondo_solidaridad,
            'retencion_fuente': retencion_fuente,
            'total_deducciones': total_deducciones,
            'salario_neto': salario_neto,
            'aporte_salud_empr': aporte_salud_empr,
            'aporte_pension_empr': aporte_pension_empr,
            'aporte_arl': aporte_arl,
            'aporte_caja': aporte_caja,
            'aporte_sena': aporte_sena,
            'aporte_icbf': aporte_icbf,
            'total_costo_empr': total_costo_empr,
            'provision_cesantias': provision_cesantias,
            'provision_int_cesantias': provision_int_cesantias,
            'provision_prima': provision_prima,
            'provision_vacaciones': provision_vacaciones,
            'total_prestaciones': total_prestaciones,
            'costo_total_empresa': total_costo_empr + total_prestaciones,
        }

    @staticmethod
    def calcular_liquidacion(empleado, motivo):
        """
        Calcula la liquidación de un empleado.
        motivo: 'renuncia' | 'despido_justa' | 'despido_sin_justa' | 'mutuo_acuerdo'
        """
        hoy = date_t.today()
        fecha_retiro  = empleado.fecha_retiro or hoy
        fecha_ingreso = empleado.fecha_ingreso
        if not fecha_ingreso:
            return None

        dias_trabajados = (fecha_retiro - fecha_ingreso).days
        anios = dias_trabajados / 365.25
        salario = empleado.salario_base
        aux_transporte = AUXILIO_TRANSPORTE_2025 if (
            empleado.auxilio_transporte and salario <= 2 * SMLMV_2025
        ) else 0
        salario_con_aux = salario + aux_transporte

        cesantias     = round(salario_con_aux * dias_trabajados / 365.25)
        int_cesantias = round(cesantias * 0.12 * dias_trabajados / 365.25)

        ultimo_1_julio = date_t(hoy.year, 7, 1) if hoy.month >= 7 else date_t(hoy.year - 1, 7, 1)
        ultimo_1_enero = date_t(hoy.year, 1, 1)
        inicio_semestre = max(ultimo_1_julio, ultimo_1_enero, fecha_ingreso)
        dias_semestre = max((fecha_retiro - inicio_semestre).days, 0)
        prima = round(salario_con_aux * dias_semestre / 360)

        vacaciones = round(salario * dias_trabajados / 730)

        indemnizacion = 0
        if motivo == 'despido_sin_justa':
            if getattr(empleado, 'tipo_contrato', 'indefinido') == 'indefinido':
                if anios < 1:
                    indemnizacion = round(salario * 30 / 30)
                elif salario <= 10 * SMLMV_2025:
                    indemnizacion = round(salario * 30 / 30 + salario * 20 / 30 * (anios - 1))
                else:
                    indemnizacion = round(salario * 20 / 30 * anios)

        total = cesantias + int_cesantias + prima + vacaciones + indemnizacion

        return {
            'fecha_ingreso': fecha_ingreso,
            'fecha_retiro': fecha_retiro,
            'dias_trabajados': dias_trabajados,
            'anios': round(anios, 2),
            'cesantias': cesantias,
            'int_cesantias': int_cesantias,
            'prima': prima,
            'vacaciones': vacaciones,
            'indemnizacion': indemnizacion,
            'total': total,
            'motivo': motivo,
        }
