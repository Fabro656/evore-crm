# routes/capacitacion.py — Modulo de Capacitacion y Evaluacion
from flask import render_template, redirect, url_for, flash, request, g
from flask_login import login_required, current_user
from extensions import db
from models import *
from utils import *
from datetime import datetime
import json, logging

APROBACION_MIN = 70  # porcentaje minimo para aprobar

def register(app):

    # ── capacitacion_index (/capacitacion) ──
    @app.route('/capacitacion')
    @login_required
    def capacitacion_index():
        cursos = CapCurso.query.filter_by(activo=True).order_by(CapCurso.orden, CapCurso.id).all()
        cid = getattr(g, 'company_id', None)
        # Progreso por curso
        progreso = {}
        for c in cursos:
            total = len([l for l in c.lecciones if l.activo])
            if total == 0:
                progreso[c.id] = {'total': 0, 'completadas': 0, 'pct': 0}
                continue
            completadas = CapProgreso.query.filter_by(
                user_id=current_user.id, company_id=cid, completado=True
            ).filter(CapProgreso.leccion_id.in_([l.id for l in c.lecciones if l.activo])).count()
            progreso[c.id] = {
                'total': total,
                'completadas': completadas,
                'pct': round(completadas / total * 100)
            }
        # Ultima evaluacion por curso
        evaluaciones = {}
        for c in cursos:
            ev = CapEvaluacion.query.filter_by(
                user_id=current_user.id, company_id=cid, curso_id=c.id
            ).order_by(CapEvaluacion.creado_en.desc()).first()
            if ev:
                evaluaciones[c.id] = ev
        # Agrupar por modulo
        modulos_orden = ['ventas', 'compras', 'produccion', 'inventario', 'contable', 'nomina', 'tareas', 'empaques']
        grupos = {}
        for c in cursos:
            key = c.modulo_crm or 'general'
            if key not in grupos:
                grupos[key] = []
            grupos[key].append(c)
        return render_template('capacitacion/index.html',
            cursos=cursos, grupos=grupos, modulos_orden=modulos_orden,
            progreso=progreso, evaluaciones=evaluaciones)

    # ── capacitacion_curso (/capacitacion/curso/<id>) ──
    @app.route('/capacitacion/curso/<int:id>')
    @login_required
    def capacitacion_curso(id):
        curso = CapCurso.query.get_or_404(id)
        lecciones = [l for l in curso.lecciones if l.activo]
        cid = getattr(g, 'company_id', None)
        completadas_ids = set()
        if cid:
            rows = CapProgreso.query.filter_by(
                user_id=current_user.id, company_id=cid, completado=True
            ).filter(CapProgreso.leccion_id.in_([l.id for l in lecciones])).all()
            completadas_ids = {r.leccion_id for r in rows}
        todas_completas = len(completadas_ids) >= len(lecciones) and len(lecciones) > 0
        # Ultima evaluacion
        evaluacion = CapEvaluacion.query.filter_by(
            user_id=current_user.id, company_id=cid, curso_id=curso.id
        ).order_by(CapEvaluacion.creado_en.desc()).first()
        return render_template('capacitacion/curso.html',
            curso=curso, lecciones=lecciones, completadas_ids=completadas_ids,
            todas_completas=todas_completas, evaluacion=evaluacion)

    # ── capacitacion_leccion (/capacitacion/leccion/<id>) ──
    @app.route('/capacitacion/leccion/<int:id>')
    @login_required
    def capacitacion_leccion(id):
        leccion = CapLeccion.query.get_or_404(id)
        curso = leccion.curso
        lecciones = [l for l in curso.lecciones if l.activo]
        idx = next((i for i, l in enumerate(lecciones) if l.id == leccion.id), 0)
        prev_l = lecciones[idx - 1] if idx > 0 else None
        next_l = lecciones[idx + 1] if idx < len(lecciones) - 1 else None
        cid = getattr(g, 'company_id', None)
        completada = False
        if cid:
            p = CapProgreso.query.filter_by(
                user_id=current_user.id, company_id=cid, leccion_id=leccion.id, completado=True
            ).first()
            completada = p is not None
        return render_template('capacitacion/leccion.html',
            leccion=leccion, curso=curso, idx=idx, total=len(lecciones),
            prev_l=prev_l, next_l=next_l, completada=completada)

    # ── capacitacion_completar (POST) ──
    @app.route('/capacitacion/leccion/<int:id>/completar', methods=['POST'])
    @login_required
    def capacitacion_completar(id):
        leccion = CapLeccion.query.get_or_404(id)
        cid = getattr(g, 'company_id', None)
        if not cid:
            flash('Error de sesion.', 'danger')
            return redirect(url_for('capacitacion_curso', id=leccion.curso_id))
        existing = CapProgreso.query.filter_by(
            user_id=current_user.id, company_id=cid, leccion_id=leccion.id
        ).first()
        if existing:
            existing.completado = True
            existing.completado_en = datetime.utcnow()
        else:
            db.session.add(CapProgreso(
                user_id=current_user.id, company_id=cid,
                leccion_id=leccion.id, completado=True,
                completado_en=datetime.utcnow()
            ))
        db.session.commit()
        # Ir a siguiente leccion o volver al curso
        lecciones = [l for l in leccion.curso.lecciones if l.activo]
        idx = next((i for i, l in enumerate(lecciones) if l.id == leccion.id), 0)
        if idx < len(lecciones) - 1:
            return redirect(url_for('capacitacion_leccion', id=lecciones[idx + 1].id))
        flash('Leccion completada. Has terminado todas las lecciones de este curso.', 'success')
        return redirect(url_for('capacitacion_curso', id=leccion.curso_id))

    # ── capacitacion_quiz (GET + POST) ──
    @app.route('/capacitacion/curso/<int:id>/quiz', methods=['GET', 'POST'])
    @login_required
    def capacitacion_quiz(id):
        curso = CapCurso.query.get_or_404(id)
        preguntas = [p for p in curso.preguntas]
        cid = getattr(g, 'company_id', None)

        if request.method == 'POST':
            if not preguntas:
                flash('Este curso no tiene preguntas.', 'warning')
                return redirect(url_for('capacitacion_curso', id=id))
            puntaje = 0
            respuestas_det = []
            for p in preguntas:
                sel = request.form.get(f'q_{p.id}')
                sel_int = int(sel) if sel is not None else -1
                correcto = sel_int == p.respuesta_correcta
                if correcto:
                    puntaje += 1
                respuestas_det.append({
                    'pregunta_id': p.id, 'seleccion': sel_int,
                    'correcto': correcto
                })
            porcentaje = round(puntaje / len(preguntas) * 100, 1)
            aprobado = porcentaje >= APROBACION_MIN
            ev = CapEvaluacion(
                user_id=current_user.id, company_id=cid, curso_id=curso.id,
                puntaje=puntaje, total_preguntas=len(preguntas),
                porcentaje=porcentaje, aprobado=aprobado,
                respuestas=json.dumps(respuestas_det)
            )
            db.session.add(ev)
            # Notificar al admin de la empresa
            try:
                admin_user = User.query.filter_by(
                    company_id=cid, rol='admin', activo=True
                ).first()
                if admin_user and admin_user.id != current_user.id:
                    estado_txt = 'Aprobado' if aprobado else 'No aprobado'
                    db.session.add(Notificacion(
                        company_id=cid,
                        user_id=admin_user.id,
                        tipo='capacitacion',
                        titulo=f'Evaluacion: {current_user.nombre} — {curso.titulo}',
                        mensaje=f'{current_user.nombre} completo "{curso.titulo}" con {porcentaje}% ({estado_txt})',
                        link=url_for('capacitacion_admin'),
                        creado_en=datetime.utcnow()
                    ))
            except Exception:
                pass
            db.session.commit()
            return redirect(url_for('capacitacion_resultado', id=curso.id))

        # GET
        for p in preguntas:
            p._opciones = json.loads(p.opciones) if p.opciones else []
        return render_template('capacitacion/quiz.html',
            curso=curso, preguntas=preguntas)

    # ── capacitacion_resultado ──
    @app.route('/capacitacion/curso/<int:id>/resultado')
    @login_required
    def capacitacion_resultado(id):
        curso = CapCurso.query.get_or_404(id)
        cid = getattr(g, 'company_id', None)
        ev = CapEvaluacion.query.filter_by(
            user_id=current_user.id, company_id=cid, curso_id=curso.id
        ).order_by(CapEvaluacion.creado_en.desc()).first()
        if not ev:
            return redirect(url_for('capacitacion_curso', id=id))
        preguntas = {p.id: p for p in curso.preguntas}
        respuestas_det = json.loads(ev.respuestas) if ev.respuestas else []
        for r in respuestas_det:
            p = preguntas.get(r['pregunta_id'])
            if p:
                r['texto'] = p.texto
                r['opciones'] = json.loads(p.opciones) if p.opciones else []
                r['correcta'] = p.respuesta_correcta
        return render_template('capacitacion/resultado.html',
            curso=curso, ev=ev, respuestas=respuestas_det)

    # ── capacitacion_admin ──
    @app.route('/capacitacion/admin')
    @login_required
    def capacitacion_admin():
        rol = _get_rol_activo(current_user)
        if rol not in ('admin', 'director_financiero', 'director_operativo'):
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('capacitacion_index'))
        cid = getattr(g, 'company_id', None)
        cursos = CapCurso.query.filter_by(activo=True).order_by(CapCurso.orden).all()
        # All users from this company
        usuarios = User.query.filter_by(company_id=cid, activo=True).order_by(User.nombre).all()
        # Build matrix: user -> curso -> latest eval
        matrix = {}
        for u in usuarios:
            matrix[u.id] = {'user': u, 'cursos': {}}
            for c in cursos:
                ev = CapEvaluacion.query.filter_by(
                    user_id=u.id, company_id=cid, curso_id=c.id
                ).order_by(CapEvaluacion.creado_en.desc()).first()
                # Progress
                total_l = len([l for l in c.lecciones if l.activo])
                comp_l = CapProgreso.query.filter_by(
                    user_id=u.id, company_id=cid, completado=True
                ).filter(CapProgreso.leccion_id.in_([l.id for l in c.lecciones if l.activo])).count() if total_l else 0
                matrix[u.id]['cursos'][c.id] = {
                    'ev': ev,
                    'progreso_pct': round(comp_l / total_l * 100) if total_l else 0
                }
        return render_template('capacitacion/admin.html',
            cursos=cursos, usuarios=usuarios, matrix=matrix)
