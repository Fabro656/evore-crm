# routes/chat.py — Sistema de chat interno e inter-empresa
from flask import render_template, redirect, url_for, flash, request, jsonify, session as flask_session
from flask_login import login_required, current_user
from extensions import db
from models import *
from utils import *
from datetime import datetime
import json, logging


def register(app):

    @app.route('/chat')
    @login_required
    def chat_index():
        """Lista de chat rooms del usuario."""
        from flask import g
        # Get rooms where user is active participant
        my_rooms = db.session.query(ChatRoom).join(
            ChatParticipant, ChatParticipant.room_id == ChatRoom.id
        ).filter(
            ChatParticipant.user_id == current_user.id,
            ChatParticipant.activo == True,
            ChatRoom.activo == True
        ).order_by(ChatRoom.creado_en.desc()).all()

        # Add last message and unread count for each room
        rooms_data = []
        for room in my_rooms:
            last_msg = ChatMessage.query.filter_by(room_id=room.id).order_by(ChatMessage.creado_en.desc()).first()
            # Count unread
            unread = 0
            try:
                unread = ChatMessage.query.filter(
                    ChatMessage.room_id == room.id,
                    ~ChatMessage.leido_por.contains(f'"{current_user.id}"'),
                    ChatMessage.user_id != current_user.id
                ).count()
            except Exception:
                pass
            # Get other participants names
            others = [p.user.nombre for p in room.participants if p.user_id != current_user.id and p.activo]
            display_name = room.nombre or ', '.join(others[:3]) or 'Chat'
            rooms_data.append({
                'room': room,
                'last_msg': last_msg,
                'unread': unread,
                'display_name': display_name,
                'others': others,
            })
        return render_template('chat/index.html', rooms=rooms_data)

    @app.route('/chat/<int:room_id>')
    @login_required
    def chat_room(room_id):
        """Ver mensajes de un chat room."""
        room = ChatRoom.query.get_or_404(room_id)
        # Verify user is participant (or admin of platform)
        participant = ChatParticipant.query.filter_by(
            room_id=room_id, user_id=current_user.id, activo=True
        ).first()
        from flask import g
        is_admin = False
        try:
            company = db.session.get(Company, g.company_id) if g.company_id else None
            is_admin = bool(company and company.es_principal and current_user.rol == 'admin')
        except Exception:
            pass
        if not participant and not is_admin:
            flash('No tienes acceso a este chat.', 'danger')
            return redirect(url_for('chat_index'))
        # Get messages
        messages = ChatMessage.query.filter_by(room_id=room_id).order_by(ChatMessage.creado_en.asc()).limit(200).all()
        # Mark as read
        try:
            uid_str = str(current_user.id)
            for msg in messages:
                if msg.user_id != current_user.id:
                    try:
                        read_list = json.loads(msg.leido_por or '[]')
                        if uid_str not in read_list and current_user.id not in read_list:
                            read_list.append(current_user.id)
                            msg.leido_por = json.dumps(read_list)
                    except Exception:
                        pass
            db.session.commit()
        except Exception:
            pass
        # Get participants
        participants = ChatParticipant.query.filter_by(room_id=room_id, activo=True).all()
        # Get all company users for adding
        all_users = []
        if is_admin or (participant and participant.rol == 'admin'):
            try:
                from flask import g
                all_users = User.query.filter_by(activo=True).order_by(User.nombre).all()
            except Exception:
                pass
        return render_template('chat/room.html', room=room, messages=messages,
                               participants=participants, is_admin=is_admin,
                               all_users=all_users, my_participant=participant)

    @app.route('/chat/<int:room_id>/enviar', methods=['POST'])
    @login_required
    def chat_enviar(room_id):
        """Enviar mensaje a un chat room."""
        room = ChatRoom.query.get_or_404(room_id)
        participant = ChatParticipant.query.filter_by(
            room_id=room_id, user_id=current_user.id, activo=True
        ).first()
        if not participant:
            return jsonify({'error': 'No tienes acceso'}), 403
        contenido = request.form.get('contenido', '').strip()
        if not contenido:
            return redirect(url_for('chat_room', room_id=room_id))
        msg = ChatMessage(room_id=room_id, user_id=current_user.id,
                          contenido=contenido, tipo='texto',
                          leido_por=json.dumps([current_user.id]))
        db.session.add(msg)
        db.session.commit()
        # If AJAX request, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': True, 'id': msg.id})
        return redirect(url_for('chat_room', room_id=room_id))

    @app.route('/chat/nuevo', methods=['GET', 'POST'])
    @login_required
    def chat_nuevo():
        """Crear nuevo chat room (interno)."""
        if request.method == 'POST':
            nombre = request.form.get('nombre', '').strip()
            user_ids = request.form.getlist('users')
            from flask import g
            room = ChatRoom(company_id=g.company_id, tipo='interno',
                            nombre=nombre or None, creado_por=current_user.id)
            db.session.add(room)
            db.session.flush()
            # Add creator as admin
            db.session.add(ChatParticipant(room_id=room.id, user_id=current_user.id,
                                           rol='admin', agregado_por=current_user.id))
            # Add selected users
            for uid in user_ids:
                try:
                    uid = int(uid)
                    if uid != current_user.id:
                        db.session.add(ChatParticipant(room_id=room.id, user_id=uid,
                                                       rol='miembro', agregado_por=current_user.id))
                except Exception:
                    pass
            # System message
            db.session.add(ChatMessage(room_id=room.id, user_id=current_user.id,
                                       contenido=f'{current_user.nombre} creó la conversacion',
                                       tipo='sistema'))
            db.session.commit()
            flash('Chat creado.', 'success')
            return redirect(url_for('chat_room', room_id=room.id))
        # Get company users for selection
        users = User.query.filter(User.activo == True, User.id != current_user.id).order_by(User.nombre).all()
        return render_template('chat/nuevo.html', users=users)

    @app.route('/chat/<int:room_id>/agregar', methods=['POST'])
    @login_required
    def chat_agregar(room_id):
        """Agregar participante a un chat (admin only)."""
        user_id = request.form.get('user_id', type=int)
        if not user_id:
            flash('Usuario no válido.', 'danger')
            return redirect(url_for('chat_room', room_id=room_id))
        # Check permission
        my_part = ChatParticipant.query.filter_by(room_id=room_id, user_id=current_user.id, activo=True).first()
        from flask import g
        company = db.session.get(Company, g.company_id) if g.company_id else None
        is_platform_admin = bool(company and company.es_principal and current_user.rol == 'admin')
        if not my_part and not is_platform_admin:
            flash('Sin permisos.', 'danger')
            return redirect(url_for('chat_index'))
        if my_part and my_part.rol not in ('admin',) and not is_platform_admin:
            flash('Solo administradores del chat pueden agregar participantes.', 'warning')
            return redirect(url_for('chat_room', room_id=room_id))
        # Check if already participant
        existing = ChatParticipant.query.filter_by(room_id=room_id, user_id=user_id).first()
        if existing:
            if not existing.activo:
                existing.activo = True
                db.session.commit()
                flash('Participante reactivado.', 'success')
            else:
                flash('Ya es participante.', 'info')
        else:
            db.session.add(ChatParticipant(room_id=room_id, user_id=user_id,
                                           rol='miembro', agregado_por=current_user.id))
            user = db.session.get(User, user_id)
            db.session.add(ChatMessage(room_id=room_id, user_id=current_user.id,
                                       contenido=f'{current_user.nombre} agregó a {user.nombre if user else "usuario"}',
                                       tipo='sistema'))
            db.session.commit()
            flash('Participante agregado.', 'success')
        return redirect(url_for('chat_room', room_id=room_id))

    @app.route('/chat/<int:room_id>/remover', methods=['POST'])
    @login_required
    def chat_remover(room_id):
        """Remover participante de un chat (admin only)."""
        user_id = request.form.get('user_id', type=int)
        if not user_id:
            return redirect(url_for('chat_room', room_id=room_id))
        my_part = ChatParticipant.query.filter_by(room_id=room_id, user_id=current_user.id, activo=True).first()
        from flask import g
        company = db.session.get(Company, g.company_id) if g.company_id else None
        is_platform_admin = bool(company and company.es_principal and current_user.rol == 'admin')
        if not is_platform_admin and (not my_part or my_part.rol != 'admin'):
            flash('Sin permisos.', 'danger')
            return redirect(url_for('chat_room', room_id=room_id))
        part = ChatParticipant.query.filter_by(room_id=room_id, user_id=user_id).first()
        if part:
            part.activo = False
            user = db.session.get(User, user_id)
            db.session.add(ChatMessage(room_id=room_id, user_id=current_user.id,
                                       contenido=f'{current_user.nombre} removió a {user.nombre if user else "usuario"}',
                                       tipo='sistema'))
            db.session.commit()
            flash('Participante removido.', 'info')
        return redirect(url_for('chat_room', room_id=room_id))

    @app.route('/api/chat/<int:room_id>/mensajes')
    @login_required
    def api_chat_mensajes(room_id):
        """JSON: mensajes nuevos para polling."""
        after_id = request.args.get('after', 0, type=int)
        participant = ChatParticipant.query.filter_by(
            room_id=room_id, user_id=current_user.id, activo=True
        ).first()
        if not participant:
            return jsonify({'messages': []})
        msgs = ChatMessage.query.filter(
            ChatMessage.room_id == room_id,
            ChatMessage.id > after_id
        ).order_by(ChatMessage.creado_en.asc()).limit(50).all()
        result = []
        for m in msgs:
            result.append({
                'id': m.id,
                'user_id': m.user_id,
                'user_name': m.user.nombre if m.user else '?',
                'contenido': m.contenido,
                'tipo': m.tipo,
                'creado_en': m.creado_en.strftime('%H:%M') if m.creado_en else '',
                'is_mine': m.user_id == current_user.id,
            })
        return jsonify({'messages': result})

    @app.route('/api/chat/unread')
    @login_required
    def api_chat_unread():
        """JSON: total de mensajes no leídos."""
        try:
            my_rooms = db.session.query(ChatRoom.id).join(
                ChatParticipant
            ).filter(
                ChatParticipant.user_id == current_user.id,
                ChatParticipant.activo == True
            ).all()
            room_ids = [r[0] for r in my_rooms]
            if not room_ids:
                return jsonify({'count': 0})
            unread = ChatMessage.query.filter(
                ChatMessage.room_id.in_(room_ids),
                ChatMessage.user_id != current_user.id,
                ~ChatMessage.leido_por.contains(str(current_user.id))
            )
            total = unread.count()
            # Include last unread message info for notification popup
            last = unread.order_by(ChatMessage.creado_en.desc()).first()
            last_info = None
            if last:
                sender = db.session.get(User, last.user_id)
                room = db.session.get(ChatRoom, last.room_id)
                last_info = {
                    'id': last.id,
                    'user': sender.nombre if sender else 'Alguien',
                    'room': room.nombre if room else 'Chat',
                    'text': (last.contenido or '')[:80],
                    'room_id': last.room_id
                }
            return jsonify({'count': total, 'last': last_info})
        except Exception:
            return jsonify({'count': 0})
