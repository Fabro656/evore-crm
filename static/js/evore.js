// ── CSRF token for AJAX requests ──
var _csrfToken=(document.querySelector('meta[name="csrf-token"]')||{}).content||'';
// Auto-inject CSRF hidden field into every POST form that doesn't have one
if(_csrfToken){document.querySelectorAll('form[method="POST"],form[method="post"]').forEach(function(f){
  if(!f.querySelector('input[name="_csrf_token"]')){
    var h=document.createElement('input');h.type='hidden';h.name='_csrf_token';h.value=_csrfToken;f.appendChild(h);
  }
});}

// ── Dock: hover=tooltip, click=open panel ──
(function(){
  var tip = document.createElement('div');
  tip.className = 'dock-tip';
  document.body.appendChild(tip);

  function showTip(icon){
    if(document.getElementById('sb').classList.contains('sb-expanded')) return;
    var label = icon.dataset.tip || '';
    if(!label) return;
    var rect = icon.getBoundingClientRect();
    tip.textContent = label;
    tip.style.left = (rect.right + 10) + 'px';
    tip.style.top = (rect.top + rect.height/2) + 'px';
    tip.style.transform = 'translateY(-50%)';
    tip.classList.add('show');
  }
  function hideTip(){ tip.classList.remove('show'); }

  var hoverTimer = null;
  // Hover = tooltip + auto-open panel after 3s
  document.querySelectorAll('.sb-nav .nav-link').forEach(function(icon){
    icon.addEventListener('mouseenter', function(){
      showTip(icon);
      clearTimeout(hoverTimer);
      var panelId = icon.dataset.dockPanel;
      if(panelId){
        hoverTimer = setTimeout(function(){
          hideTip();
          openDockPanel(panelId, icon);
        }, 2500);
      }
    });
    icon.addEventListener('mouseleave', function(){
      hideTip();
      clearTimeout(hoverTimer);
    });
  });

  // Click = open panel immediately (stop propagation to prevent closing sidebar on mobile)
  document.querySelectorAll('.sb-nav .nav-link').forEach(function(icon){
    icon.addEventListener('click', function(e){
      clearTimeout(hoverTimer);
      hideTip();
      var panelId = icon.dataset.dockPanel;
      if(panelId){
        e.preventDefault();
        e.stopPropagation();
        openDockPanel(panelId, icon);
      }
    });
  });

  window.openDockPanel = function(panelId, icon){
    closeDockPanel();
    var panel = document.getElementById('dp-' + panelId);
    if(!panel) return;
    var sb = document.getElementById('sb');
    var isExpanded = sb && sb.classList.contains('sb-expanded');
    var isMob = window.innerWidth <= 768;
    var vh = window.innerHeight;
    var pad = 12;

    // Mostrar off-screen para medir alto real
    panel.style.visibility = 'hidden';
    panel.style.display = 'block';
    var panelH = panel.offsetHeight;
    panel.style.visibility = '';

    if (isMob) {
      // Mobile: centrado horizontal, desde abajo
      panel.style.left = pad + 'px';
      panel.style.right = pad + 'px';
      panel.style.width = 'auto';
      var maxH = vh - 2 * pad;
      if (panelH > maxH) {
        panel.style.maxHeight = maxH + 'px';
      }
      panel.style.top = Math.max(pad, vh - panelH - pad) + 'px';
    } else {
      // Desktop: al lado del dock
      panel.style.left = (isExpanded ? 244 : 68) + 'px';
      panel.style.removeProperty('right');
      panel.style.removeProperty('width');
      var rect = icon.getBoundingClientRect();
      var iconCenterY = rect.top + rect.height / 2;

      // Calcular max-height disponible
      var maxAvailable = vh - 2 * pad;
      if (panelH > maxAvailable) {
        panel.style.maxHeight = maxAvailable + 'px';
        panelH = maxAvailable;
      }

      // Intentar centrar verticalmente respecto al icono
      var top = iconCenterY - panelH / 2;

      // Clamp: no salir por arriba ni por abajo
      if (top + panelH > vh - pad) {
        top = vh - panelH - pad;
      }
      if (top < pad) {
        top = pad;
      }

      panel.style.top = top + 'px';
    }

    document.getElementById('dock-overlay').style.display = 'block';
  };

  // Submenu hover explanations
  var subTipTimer = null;
  var SUB_TIPS = {
    'Clientes':'Directorio de clientes con contactos e info bancaria',
    'Productos':'Catalogo de productos terminados con recetas',
    'Ventas':'Pipeline de ventas con seguimiento financiero',
    'Cotizaciones':'Propuestas comerciales con calculo IVA y PDF',
    'Servicios':'Catalogo de servicios sin inventario',
    'Proveedores':'Directorio de proveedores y datos de contacto',
    'Cotizaciones prov.':'Cotizaciones recibidas de proveedores',
    'Ordenes de Compra':'OC con multi-cotizacion y asiento auto',
    'Registro compras':'Registro de materiales comprados',
    'Dashboard':'Panel de produccion con estadisticas',
    'Ordenes':'Ordenes de produccion activas y completadas',
    'Gantt':'Diagrama de tiempos de produccion',
    'Recepcion MP':'Recibir material de ordenes de compra',
    'Contabilidad':'Dashboard financiero con ingresos y egresos',
    'Asientos contables':'Confirma pagos de OC y cobros de ventas',
    'Plan de Cuentas':'PUC colombiano con 102 cuentas',
    'Gastos':'Registro de gastos operativos con estado de pago',
    'Balance de Prueba':'Verificar que debitos = creditos',
    'Balance General':'Activos = Pasivos + Patrimonio',
    'Estado de Resultados':'Ingresos - Gastos = Utilidad',
    'Reportes':'Reportes financieros exportables',
    'Empleados':'Lista de empleados con nomina',
    'Nuevo empleado':'Registrar nuevo empleado',
    'Parametros':'Tasas de nomina colombiana',
    'Pendientes':'Solicitudes esperando aprobacion',
    'Mis solicitudes':'Solicitudes que tu has enviado',
    'Usuarios':'Crear y gestionar usuarios del sistema',
    'Actividad':'Log de todas las acciones del sistema',
    'Empresa':'Configuracion de datos de la empresa',
    'Transportistas':'Empresas de transporte con tipo de vehiculo',
    'Empaques':'Simulador de empaque y logistica',
    'Documentos':'Documentos legales con alertas de vencimiento',
    'Buscador global':'Busca en todo el CRM',
  };
  document.addEventListener('mouseenter',function(e){
    var link = e.target.closest('.dock-panel-link');
    if(!link) return;
    var text = link.textContent.trim();
    var explanation = SUB_TIPS[text];
    if(!explanation) return;
    clearTimeout(subTipTimer);
    subTipTimer = setTimeout(function(){
      var tip = document.querySelector('.dock-tip');
      if(!tip) return;
      var rect = link.getBoundingClientRect();
      tip.textContent = explanation;
      tip.style.left = (rect.right + 8) + 'px';
      tip.style.top = (rect.top + rect.height/2) + 'px';
      tip.style.transform = 'translateY(-50%)';
      tip.classList.add('show');
    }, 2000);
  },true);
  document.addEventListener('mouseleave',function(e){
    if(e.target.closest('.dock-panel-link')){
      clearTimeout(subTipTimer);
      var tip = document.querySelector('.dock-tip');
      if(tip) tip.classList.remove('show');
    }
  },true);

  // ── Guias contextuales en cada dock panel ──
  var PANEL_GUIDES = {
    'dp-home': '<strong>Home</strong> es tu centro de control.<br>• Revisa KPIs de ventas e ingresos<br>• Ve tickets pendientes y ventas recientes<br>• Aprobaciones que necesitan tu atención<br>• Calendario del día y próximos 7 días<br>• Notas recientes de todo el equipo',
    'dp-tickets': '<strong>Tickets</strong> organizan el trabajo.<br>• Crea tickets con prioridad y asignados<br>• Tipos: Ticket (requiere acción) o Notificación (informativa)<br>• Categorías: calidad, logística, pago, general<br>• Se crean automáticamente por problemas de calidad o nómina pendiente<br>• Cada ticket tiene comentarios para seguimiento',
    'dp-calendario': '<strong>Calendario</strong> para eventos y recordatorios.<br>• Click en un día para crear evento<br>• Navega por mes y año con selectores<br>• Tipos: cita, reunión, recordatorio<br>• Los eventos de producción se sincronizan automáticamente',
    'dp-notas': '<strong>Notas</strong> vinculadas a entidades.<br>• Vincular a OC, ventas o proveedores<br>• Tipos: nota, alerta, seguimiento, resolución<br>• Marcar como resuelta cuando se completa<br>• Filtrar por tipo, estado o entidad',
    'dp-comercial': '<strong>Flujo comercial:</strong><br>1. Registra <strong>Clientes</strong> con contactos<br>2. Crea <strong>Cotizaciones</strong> con cálculo IVA y PDF<br>3. Convierte cotización en <strong>Venta</strong><br>4. Al crear venta se genera asiento contable de ingreso<br>5. Anticipo solo se confirma desde Asientos Contables<br>6. Asigna transportista y envía con remisión<br><br>• <strong>Productos</strong>: catálogo con recetas/BOM<br>• <strong>Servicios</strong>: sin inventario',
    'dp-compras': '<strong>Flujo de compras:</strong><br>1. Registra <strong>Proveedores</strong> con datos de contacto<br>2. Crea <strong>Cotizaciones de proveedor</strong> con precios y plazos<br>3. Crea <strong>Orden de Compra</strong> seleccionando múltiples cotizaciones<br>4. Se genera asiento contable de egreso automáticamente<br>5. Confirma pago desde Asientos Contables (parcial o total)<br>6. La OC cambia de estado automáticamente<br>7. Recibe material desde Producción > Registro compras',
    'dp-inventario': '<strong>Inventario</strong> de productos terminados.<br>• Stock con alertas de mínimo<br>• Lotes con trazabilidad FIFO y vencimiento<br>• Multi-ingreso para registrar varios a la vez<br>• Al entregar venta, stock se descuenta automáticamente',
    'dp-produccion': '<strong>Producción</strong> y manufactura.<br>• <strong>Dashboard</strong>: estadísticas de compras y órdenes<br>• <strong>Órdenes</strong>: producción pendiente y en curso<br>• <strong>Gantt</strong>: diagrama de tiempos<br>• <strong>Recepción MP</strong>: recibir material de OC (auto-actualiza stock)<br>• Reportar problemas de calidad crea tickets automáticos',
    'dp-logistica': '<strong>Logística</strong> y transporte.<br>• <strong>Transportistas</strong>: registro con tipo de vehículo y capacidad<br>• <strong>Empaques</strong>: simulador de caja y pallet<br>• <strong>Calculadora de envío</strong>: costo FTL vs paquetería, tarifas editables, margen, transportistas compatibles',
    'dp-finanzas': '<strong>Finanzas</strong> y contabilidad.<br>• <strong>Contabilidad</strong>: dashboard con ingresos/egresos/utilidad<br>• <strong>Asientos contables</strong>: generados (desde OC/ventas) y manuales. Confirmar pagos aquí cambia estado de OC/ventas<br>• <strong>PUC</strong>: Plan Único de Cuentas colombiano (102 cuentas)<br>• <strong>Gastos</strong>: operativos con estado pagado/pendiente<br>• <strong>Balances</strong>: prueba, general, estado de resultados<br>• <strong>Reportes</strong>: exportables',
    'dp-legal': '<strong>Legal</strong> y documentos.<br>• Permisos sanitarios, INVIMA, NSO, contratos, licencias<br>• Alertas de vencimiento con días de anticipación<br>• Búsqueda por título, número o entidad<br>• Vincular a clientes y proveedores',
    'dp-nomina': '<strong>Nómina</strong> colombiana.<br>• Cerrar nómina con prorrateo por días trabajados<br>• Retiro: renuncia, despido justificado, despido no justificado<br>• Liquidación se registra como gasto de inmediato<br>• Ticket automático si no se cierra nómina a tiempo<br>• Parámetros: SMLMV, ARL, cesantías, etc.',
    'dp-aprobaciones': '<strong>Aprobaciones</strong> de procesos.<br>• Solicitar aprobación en OC, ventas, cotizaciones o asientos<br>• El proceso se BLOQUEA hasta aprobar<br>• Opciones: Aprobar, Enviar a revisión, Rechazar<br>• Admin y Director Financiero se auto-aprueban<br>• Vista detallada con info del solicitante y entidad',
    'dp-admin': '<strong>Administración</strong> del sistema.<br>• <strong>Usuarios</strong>: crear con rol y módulos personalizados<br>• <strong>Actividad</strong>: log de todas las acciones del sistema<br>• <strong>Empresa</strong>: nombre, NIT, dirección, firma digital',
  };
  // Inyectar guias en cada panel
  document.querySelectorAll('.dock-panel').forEach(function(panel){
    var guide = PANEL_GUIDES[panel.id];
    if(!guide) return;
    var guideDiv = document.createElement('div');
    guideDiv.style.cssText = 'padding:0 12px 10px;border-top:1px solid var(--border)';
    guideDiv.innerHTML = '<div onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\'" style="cursor:pointer;padding:6px 0;font-size:.72rem;color:var(--text2);display:flex;align-items:center;gap:4px"><i class="bi bi-book"></i>Guía del módulo <i class="bi bi-chevron-down" style="margin-left:auto;font-size:.6rem"></i></div>'
      +'<div style="display:none;font-size:.73rem;color:var(--text2);line-height:1.6;padding:4px 0">'+guide+'</div>';
    panel.appendChild(guideDiv);
  });

  window.closeDockPanel = function(){
    document.querySelectorAll('.dock-panel').forEach(function(p){ p.style.display = 'none'; });
    document.getElementById('dock-overlay').style.display = 'none';
    // Reset finanzas sub-panels to main view
    var finMain = document.getElementById('fin-main');
    if(finMain) finMain.style.display = '';
    document.querySelectorAll('.fin-sub').forEach(function(s){ s.style.display = 'none'; });
    hideTip();
  };

  // ── Finanzas: category → sub-panel navigation ──
  document.querySelectorAll('.fin-cat').forEach(function(btn){
    btn.addEventListener('click', function(){
      var target = btn.dataset.fin;
      var sub = document.getElementById('fin-' + target);
      if(!sub) return;
      document.getElementById('fin-main').style.display = 'none';
      sub.style.display = '';
    });
  });
  document.querySelectorAll('.fin-back').forEach(function(btn){
    btn.addEventListener('click', function(){
      btn.closest('.fin-sub').style.display = 'none';
      document.getElementById('fin-main').style.display = '';
    });
  });
})();

// ── Toggle sidebar lite/expanded ──
function toggleSidebar(){
  var sb = document.getElementById('sb');
  var main = document.getElementById('main');
  var icon = document.getElementById('sb-expand-icon');
  var expanded = sb.classList.toggle('sb-expanded');
  main.style.marginLeft = expanded ? '240px' : '64px';
  main.style.transition = 'margin-left .25s cubic-bezier(.4,0,.2,1)';
  icon.className = expanded ? 'bi bi-x-lg' : 'bi bi-list';
  // Save preference
  localStorage.setItem('evore_sb_expanded', expanded ? '1' : '0');
}
// Restore on load
(function(){
  if(localStorage.getItem('evore_sb_expanded')==='1'){
    var sb = document.getElementById('sb');
    var main = document.getElementById('main');
    var icon = document.getElementById('sb-expand-icon');
    if(sb && main && icon){
      sb.classList.add('sb-expanded');
      main.style.marginLeft = '240px';
      icon.className = 'bi bi-x-lg';
    }
  }
})();

// ── Block from line 1351 ──
// ── Sidebar mobile drawer + scroll persistence ─────────────────────────
function openSB(){
  document.getElementById('sb').classList.add('sb-open');
  document.getElementById('sb-overlay').classList.add('open');
  document.body.style.overflow='hidden';
}
function closeSB(){
  document.getElementById('sb').classList.remove('sb-open');
  document.getElementById('sb-overlay').classList.remove('open');
  document.body.style.overflow='';
}
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeSB();});
document.querySelectorAll('#sb .nav-link').forEach(function(el){
  el.addEventListener('click',function(){if(window.innerWidth<=768)closeSB();});
});
// Sidebar scroll position persistence
(function(){
  var sbNav=document.querySelector('.sb-nav');
  if(!sbNav) return;
  var saved=sessionStorage.getItem('sb_scroll');
  if(saved) sbNav.scrollTop=parseInt(saved);
  // Save before leaving page
  window.addEventListener('beforeunload',function(){
    sessionStorage.setItem('sb_scroll', sbNav.scrollTop);
  });
  // Also save on link click
  document.querySelectorAll('#sb a').forEach(function(a){
    a.addEventListener('click',function(){
      sessionStorage.setItem('sb_scroll', sbNav.scrollTop);
    });
  });
})();
// Notificaciones
function toggleNotif(e){
  e.stopPropagation();
  var dd=document.getElementById('notifDd');
  if(dd.style.display==='block'){dd.style.display='none';return;}
  dd.style.display='block';
  fetch('/notificaciones/recientes').then(r=>r.json()).then(data=>{
    var html='';
    if(data.length===0){html='<div class="p-3 text-center text-muted" style="font-size:.8rem">Sin notificaciones</div>';}
    else{data.forEach(n=>{html+='<div class="notif-item'+(n.leida?'':' unread')+'" onclick="marcarLeida(event,this,'+n.id+')">'
      +'<div class="ni-title">'+n.titulo+'</div>'
      +'<div class="ni-msg">'+n.mensaje+'</div>'
      +'<div class="ni-time">'+n.tiempo+'</div>'
      +'<a href="'+n.url+'" style="display:none" id="notif-link-'+n.id+'"></a></div>';});}
    document.getElementById('notifList').innerHTML=html;
  }).catch(()=>{});
}
function marcarLeida(e,el,id){
  e.stopPropagation();
  fetch('/notificaciones/'+id+'/leida',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':_csrfToken}})
    .then(()=>{
      el.parentElement.removeChild(el);
      var badge=document.getElementById('notif-badge');
      if(badge){var c=parseInt(badge.textContent||0)-1;if(c<=0){if(badge.parentElement)badge.parentElement.removeChild(badge);}else badge.textContent=c;}
      var dest=document.getElementById('notif-link-'+id);
      if(dest&&dest.href&&dest.href!=='#'){setTimeout(function(){window.location=dest.href;},100);}
    });
}
document.addEventListener('click',function(e){
  var dd=document.getElementById('notifDd');
  if(dd&&!dd.contains(e.target)&&e.target.id!=='notifBtn')dd.style.display='none';
});
// ── Overlay Buscador ──────────────────────────
var _srchTimer=null;
function abrirBuscador(){
  document.getElementById('searchOverlay').style.display='block';
  setTimeout(function(){document.getElementById('searchInput').focus();},50);
  document.getElementById('searchResults').innerHTML='<div style="text-align:center;padding:2rem;color:var(--text2);font-size:.85rem"><i class="bi bi-search" style="font-size:1.5rem;display:block;margin-bottom:.5rem;opacity:.35"></i>Escribe para buscar en todo el sistema</div>';
  document.getElementById('searchInput').value='';
}
function cerrarBuscador(){
  document.getElementById('searchOverlay').style.display='none';
}
function handleSearchKey(e){
  if(e.key==='Escape') cerrarBuscador();
  if(e.key==='Enter'){
    var q=document.getElementById('searchInput').value.trim();
    if(q) window.location='/buscador?q='+encodeURIComponent(q);
  }
}
function doBuscar(q){
  clearTimeout(_srchTimer);
  if(!q||q.length<2){
    document.getElementById('searchResults').innerHTML='<div style="text-align:center;padding:2rem;color:var(--text2);font-size:.85rem"><i class="bi bi-search" style="font-size:1.5rem;display:block;margin-bottom:.5rem;opacity:.35"></i>Escribe para buscar en todo el sistema</div>';
    return;
  }
  document.getElementById('searchResults').innerHTML='<div style="text-align:center;padding:1.5rem;color:var(--text2);font-size:.85rem"><i class="bi bi-hourglass-split"></i> Buscando...</div>';
  _srchTimer=setTimeout(function(){
    fetch('/api/buscar?q='+encodeURIComponent(q),{headers:{'X-Requested-With':'XMLHttpRequest'}})
      .then(function(r){return r.json();})
      .then(function(data){
        var html='';
        if(!data.results||data.results.length===0){
          html='<div class="sr-empty">'+
            '<i class="bi bi-emoji-frown" style="font-size:1.3rem;display:block;margin-bottom:.5rem;opacity:.35"></i>'+
            'Sin resultados para <em>'+q+'</em></div>';
        } else {
          data.results.forEach(function(r){
            html+='<a href="'+r.url+'" class="sr-item" onclick="cerrarBuscador()">'
              +'<span class="sr-icon" style="background:'+r.color+'18"><i class="bi bi-'+r.icon+'" style="color:'+r.color+'"></i></span>'
              +'<span class="sr-body"><span class="sr-label">'+r.label+'</span>'
              +(r.sub?'<span class="sr-sub">'+r.sub+'</span>':'')+'</span>'
              +'<span class="sr-badge">'+r.type+'</span></a>';
          });
          html+='<div class="sr-footer"><a href="/buscador?q='+encodeURIComponent(q)+'" onclick="cerrarBuscador()">Ver todos los resultados →</a></div>';
        }
        document.getElementById('searchResults').innerHTML=html;
      })
      .catch(function(){document.getElementById('searchResults').innerHTML='<div style="text-align:center;padding:1.5rem;color:var(--text2);font-size:.85rem">Error al buscar</div>';});
  }, 300);
}
// Ctrl+K shortcut to open search
document.addEventListener('keydown',function(e){
  if((e.ctrlKey||e.metaKey)&&e.key==='k'){e.preventDefault();abrirBuscador();}
});

// ── Block from line 1470 ──
/* ── Auto-título global ─────────────────────────────────────────
   setupAutoTitulo('#idTitulo', ['#campo1','#campo2',...])
   Rellena el campo título uniendo los valores de los campos fuente
   con ", ". Si el usuario edita el título manualmente, deja de
   rellenarlo automáticamente.
   ─────────────────────────────────────────────────────────────── */
function setupAutoTitulo(tituloSel, sourceIds){
  var tEl = document.querySelector(tituloSel);
  if(!tEl) return;
  function build(){
    if(tEl._editadoManual) return;
    var partes = [];
    sourceIds.forEach(function(sid){
      var el = document.querySelector(sid);
      if(!el) return;
      var v = '';
      if(el.tagName === 'SELECT'){
        var o = el.options[el.selectedIndex];
        v = (o && o.value) ? o.text : '';
      } else {
        v = (el.value || '').trim();
      }
      if(el.type === 'date' && v){
        try{
          var d = new Date(v + 'T00:00:00');
          v = d.toLocaleDateString('es-CO',{day:'2-digit',month:'2-digit',year:'numeric'});
        }catch(e){}
      }
      if(v) partes.push(v);
    });
    if(partes.length) tEl.value = partes.join(', ');
  }
  tEl.addEventListener('input', function(){ this._editadoManual = true; });
  sourceIds.forEach(function(sid){
    var el = document.querySelector(sid);
    if(el){ el.addEventListener('change', build); el.addEventListener('input', build); }
  });
  build();
}
function copiarTexto(el,txt){
  navigator.clipboard.writeText(txt).then(function(){
    var ic=el.querySelector('.bi');
    if(ic){ic.className='bi bi-check2';}
    setTimeout(function(){if(ic)ic.className='bi bi-clipboard ms-1';},1500);
  });
}

// ── Block from line 1518 ──
(function(){
  var _t=null,_LIMIT=5*60*1000;
  function _reset(){clearTimeout(_t);_t=setTimeout(function(){window.location='/logout';},_LIMIT);}
  ['mousemove','keypress','click','scroll','touchstart'].forEach(function(e){document.addEventListener(e,_reset,{passive:true});});
  _reset();
})();

// ── Block from line 1741 ──
var _obStep=0,_obTotal=10;
function goStep(n){
  _obStep=n;
  /* Manual slide — override Bootstrap's transform with opacity fade */
  var items=document.querySelectorAll('#onboardCarousel .carousel-item');
  items.forEach(function(el,i){
    el.classList.toggle('active',i===n);
  });
  document.querySelectorAll('.ob-dot').forEach(function(d,i){d.className='ob-dot'+(i===n?' ob-dot-active':'');});
  document.getElementById('btnObPrev').style.visibility=n>0?'visible':'hidden';
  var isLast=n===_obTotal-1;
  var btnNext=document.getElementById('btnObNext');
  var btnFin=document.getElementById('btnObFin');
  if(isLast){
    btnNext.style.visibility='hidden'; btnNext.style.position='absolute'; btnNext.style.pointerEvents='none';
    btnFin.style.visibility='visible'; btnFin.style.position=''; btnFin.style.pointerEvents='';
  } else {
    btnNext.style.visibility='visible'; btnNext.style.position=''; btnNext.style.pointerEvents='';
    btnFin.style.visibility='hidden'; btnFin.style.position='absolute'; btnFin.style.pointerEvents='none';
  }
  document.getElementById('obStepLbl').textContent=(n+1)+'/'+_obTotal;
}
function obNav(dir){goStep(Math.min(Math.max(_obStep+dir,0),_obTotal-1));}
function cerrarOnboarding(){
  if(document.getElementById('chkNoMostrar').checked){
    fetch('/onboarding/dismiss',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':_csrfToken}});
  }
  bootstrap.Modal.getInstance(document.getElementById('modalOnboarding')).hide();
}
/* Initialize step 0 on page load */
document.addEventListener('DOMContentLoaded',function(){ try{ goStep(0); }catch(e){} });

// ── Block from line 1978 ──
// Theme toggle
(function(){
  var t = localStorage.getItem('evore_theme') || 'light';
  document.documentElement.setAttribute('data-theme', t);
  function updateIcon(){
    var t = document.documentElement.getAttribute('data-theme');
    var el = document.getElementById('themeIcon');
    if(el) el.className = t==='dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
  }
  window.toggleTheme = function(){
    var cur = document.documentElement.getAttribute('data-theme');
    var next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('evore_theme', next);
    updateIcon();
  };
  document.addEventListener('DOMContentLoaded', updateIcon);
})();
// -- Demo Layout Toggle --
(function(){
  var l=localStorage.getItem('evore_layout')||'default';
  if(l==='horizon') document.documentElement.setAttribute('data-layout','horizon');
  window.toggleDemoLayout=function(){
    var cur=document.documentElement.getAttribute('data-layout')||'default';
    var next=cur==='horizon'?'default':'horizon';
    if(next==='horizon'){document.documentElement.setAttribute('data-layout','horizon');}
    else{document.documentElement.removeAttribute('data-layout');}
    localStorage.setItem('evore_layout',next);
    var lbl=document.getElementById('demoLabel');
    if(lbl) lbl.textContent=next==='horizon'?'Default':'Demo';
  };
  var lbl=document.getElementById('demoLabel');
  if(lbl&&l==='horizon') lbl.textContent='Default';
})();

// ── Block from line 2256 ──
// ── CSRF: auto-inject hidden token into every POST form ─────────────────
(function(){
  var t=document.querySelector('meta[name="csrf-token"]');
  if(!t) return;
  var tok=t.getAttribute('content');
  if(!tok) return;
  document.querySelectorAll('form[method="post"],form[method="POST"]').forEach(function(f){
    if(!f.querySelector('input[name="_csrf_token"]')){
      var h=document.createElement('input');
      h.type='hidden'; h.name='_csrf_token'; h.value=tok;
      f.appendChild(h);
    }
  });
  // Also send token header in non-GET fetch/XHR requests
  var origFetch=window.fetch;
  window.fetch=function(url,opts){
    opts=opts||{};
    if(opts.method && opts.method.toUpperCase()!=='GET'){
      opts.headers=Object.assign({'X-CSRF-Token':tok},opts.headers||{});
    }
    return origFetch(url,opts);
  };
  var origOpen=XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open=function(method){
    this._csrf_method=method;
    return origOpen.apply(this,arguments);
  };
  var origSend=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send=function(){
    if(this._csrf_method && this._csrf_method.toUpperCase()!=='GET'){
      try{this.setRequestHeader('X-CSRF-Token',tok);}catch(e){}
    }
    return origSend.apply(this,arguments);
  };
})();

// ── Block from line 2354 ──
var _chatOpen = false;
var _chatRoomId = null;
var _chatLastMsgId = 0;
var _chatPollTimer = null;
var _chatRooms = [];
var _chatUnreadPerRoom = {};

function toggleChatPanel(){
  var p = document.getElementById('chatPanel');
  _chatOpen = !_chatOpen;
  p.style.display = _chatOpen ? 'flex' : 'none';
  if(_chatOpen){
    // Restore saved position and size
    var pos = JSON.parse(localStorage.getItem('evore_chat_pos') || 'null');
    if(pos){p.style.top=pos.top;p.style.left=pos.left;p.style.right='auto';p.style.bottom='auto'}
    var size = JSON.parse(localStorage.getItem('evore_chat_size') || 'null');
    if(size){p.style.width=size.w;p.style.height=size.h}
    chatLoadRooms();
    // Save size on resize
    new ResizeObserver(function(){
      localStorage.setItem('evore_chat_size',JSON.stringify({w:p.style.width||p.offsetWidth+'px',h:p.style.height||p.offsetHeight+'px'}));
    }).observe(p);
  }
}

// ── Draggable chat panel ──
(function(){
  var handle=document.getElementById('chatDragHandle');
  if(!handle) return;
  var panel=document.getElementById('chatPanel');
  var dragging=false,startX,startY,startLeft,startTop;

  handle.addEventListener('mousedown',startDrag);
  handle.addEventListener('touchstart',startDrag,{passive:false});

  function startDrag(e){
    dragging=true;
    handle.style.cursor='grabbing';
    var ev=e.touches?e.touches[0]:e;
    startX=ev.clientX;startY=ev.clientY;
    var rect=panel.getBoundingClientRect();
    startLeft=rect.left;startTop=rect.top;
    e.preventDefault();
    document.addEventListener('mousemove',onDrag);
    document.addEventListener('mouseup',stopDrag);
    document.addEventListener('touchmove',onDrag,{passive:false});
    document.addEventListener('touchend',stopDrag);
  }
  function onDrag(e){
    if(!dragging) return;
    var ev=e.touches?e.touches[0]:e;
    var dx=ev.clientX-startX,dy=ev.clientY-startY;
    var newLeft=Math.max(0,Math.min(window.innerWidth-100,startLeft+dx));
    var newTop=Math.max(0,Math.min(window.innerHeight-100,startTop+dy));
    panel.style.left=newLeft+'px';
    panel.style.top=newTop+'px';
    panel.style.right='auto';panel.style.bottom='auto';
    e.preventDefault();
  }
  function stopDrag(){
    dragging=false;
    handle.style.cursor='grab';
    document.removeEventListener('mousemove',onDrag);
    document.removeEventListener('mouseup',stopDrag);
    document.removeEventListener('touchmove',onDrag);
    document.removeEventListener('touchend',stopDrag);
    // Save position
    localStorage.setItem('evore_chat_pos',JSON.stringify({top:panel.style.top,left:panel.style.left}));
  }
})();

function chatLoadRooms(){
  fetch('/chat').then(r => r.text()).then(html => {
    var tmp = document.createElement('div');
    tmp.innerHTML = html;
    var links = tmp.querySelectorAll('a[href*="/chat/"]');
    _chatRooms = [];
    links.forEach(function(a){
      var match = a.getAttribute('href').match(/\/chat\/(\d+)/);
      if(!match) return;
      // Extract display name from the link content
      var nameEl = a.querySelector('[style*="font-weight:600"]');
      var name = nameEl ? nameEl.textContent.trim() : 'Chat';
      _chatRooms.push({id: parseInt(match[1]), name: name.substring(0, 20)});
    });
    chatRenderTabs();
    if(_chatRooms.length && !_chatRoomId){
      var lastChat = parseInt(localStorage.getItem('evore_last_chat'));
      var found = lastChat && _chatRooms.find(function(r){return r.id===lastChat;});
      chatOpenRoom(found ? lastChat : _chatRooms[0].id);
    }
  }).catch(function(){});
}

function chatRenderTabs(){
  var list = document.getElementById('chatRoomList');
  if(!list) return;
  if(!_chatRooms.length){ list.innerHTML = '<div style="padding:1rem;text-align:center;color:var(--text2);font-size:.75rem">Sin conversaciones</div>'; return; }
  var html = '';
  _chatRooms.forEach(function(r){
    var active = r.id === _chatRoomId;
    var unread = _chatUnreadPerRoom[String(r.id)] || 0;
    html += '<div onclick="chatOpenRoom('+r.id+')" style="padding:.6rem .7rem;cursor:pointer;border-left:3px solid '+(active?'var(--ac)':'transparent')+';background:'+(active?'var(--sb-hover)':'transparent')+';transition:all .12s;display:flex;align-items:center;gap:.5rem;border-bottom:1px solid var(--border)">'
      +'<div style="width:28px;height:28px;border-radius:8px;background:'+(active?'var(--ac)':'var(--surface2)')+';display:flex;align-items:center;justify-content:center;color:'+(active?'#fff':'var(--text2)')+';font-size:.65rem;font-weight:700;flex-shrink:0">'+r.name.charAt(0).toUpperCase()+'</div>'
      +'<div style="flex:1;min-width:0;overflow:hidden"><div style="font-size:.72rem;font-weight:'+(active?'600':'400')+';color:'+(active?'var(--text)':'var(--text2)')+';white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+r.name+'</div></div>'
      +(unread && !active?'<span style="min-width:16px;height:16px;border-radius:8px;background:var(--red);color:#fff;font-size:.55rem;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0">'+unread+'</span>':'')
      +'</div>';
  });
  list.innerHTML = html;
}

function chatCloseTab(roomId){
  _chatRooms = _chatRooms.filter(function(r){ return r.id !== roomId; });
  if(_chatRoomId === roomId){
    if(_chatPollTimer) clearInterval(_chatPollTimer);
    _chatRoomId = null;
    _chatLastMsgId = 0;
    if(_chatRooms.length){
      chatOpenRoom(_chatRooms[0].id);
    } else {
      document.getElementById('chatMsgs').innerHTML = '<div style="padding:30px 16px;text-align:center;color:var(--text2)"><i class="bi bi-chat-dots" style="font-size:1.8rem;display:block;margin-bottom:6px"></i><span style="font-size:.78rem">Selecciona o crea una conversación</span></div>';
      document.getElementById('chatInput').style.display='none';
    }
  }
  chatRenderTabs();
}

function chatCreateInline(){
  var msgs = document.getElementById('chatMsgs');
  msgs.innerHTML = '<div style="padding:16px"><div style="font-weight:700;margin-bottom:8px;font-size:.85rem">Nueva conversacion</div>'
    +'<input type="text" id="chatNewName" placeholder="Nombre (opcional)" style="width:100%;padding:6px 10px;border:1.5px solid var(--border);border-radius:8px;font-size:.82rem;margin-bottom:8px;background:var(--input-bg);color:var(--text)">'
    +'<div style="font-size:.75rem;color:var(--text2);margin-bottom:6px">Selecciona participantes:</div>'
    +'<div id="chatNewUsers" style="max-height:200px;overflow-y:auto">Cargando...</div>'
    +'<button onclick="chatCreateSubmit()" style="width:100%;padding:8px;background:var(--ac);color:#fff;border:none;border-radius:8px;font-size:.82rem;font-weight:600;cursor:pointer;margin-top:8px"><i class="bi bi-chat-dots me-1"></i>Crear</button></div>';
  document.getElementById('chatInput').style.display='none';
  // Load users
  fetch('/chat/nuevo').then(r=>r.text()).then(html=>{
    var tmp=document.createElement('div'); tmp.innerHTML=html;
    var labels=tmp.querySelectorAll('label.d-flex');
    var usersHtml='';
    labels.forEach(function(l){
      var input=l.querySelector('input[type=checkbox]');
      var name=l.querySelector('[style*="font-weight:600"]');
      if(input&&name){
        usersHtml+='<label style="display:flex;align-items:center;gap:8px;padding:6px 4px;cursor:pointer;font-size:.82rem"><input type="checkbox" class="chatNewUserCb" value="'+input.value+'"> '+name.textContent.trim()+'</label>';
      }
    });
    document.getElementById('chatNewUsers').innerHTML=usersHtml||'<span style="color:var(--text2);font-size:.8rem">Sin usuarios disponibles</span>';
  }).catch(function(){document.getElementById('chatNewUsers').innerHTML='Error';});
}

function chatSendFile(input){
  if(!input.files.length || !_chatRoomId) return;
  var file = input.files[0];
  var maxSize = 10*1024*1024; // 10MB
  if(file.size > maxSize){alert('Archivo max 10MB'); input.value=''; return;}
  // Show file message optimistically
  var container = document.getElementById('chatMsgs');
  var div = document.createElement('div');
  div.style='display:flex;justify-content:flex-end';
  div.innerHTML='<div style="max-width:80%;padding:8px 12px;border-radius:16px 16px 4px 16px;font-size:.82rem;background:var(--ac);color:#fff;opacity:.7"><i class="bi bi-paperclip me-1"></i>'+file.name+'</div>';
  container.appendChild(div);
  container.scrollTop=container.scrollHeight;
  // Send
  var fd = new FormData();
  fd.append('contenido', '📎 '+file.name+' ('+Math.round(file.size/1024)+'KB)');
  fd.append('_csrf_token', _csrfToken);
  fetch('/chat/'+_chatRoomId+'/enviar',{method:'POST',body:fd,headers:{'X-Requested-With':'XMLHttpRequest'}})
    .then(function(){div.querySelector('div').style.opacity='1';})
    .catch(function(){div.querySelector('div').style.background='#C23934';});
  input.value='';
}

function chatCreateSubmit(){
  var name=document.getElementById('chatNewName').value.trim();
  var cbs=document.querySelectorAll('.chatNewUserCb:checked');
  var fd=new FormData();
  fd.append('nombre',name);
  fd.append('_csrf_token',_csrfToken);
  cbs.forEach(function(cb){fd.append('users',cb.value);});
  fetch('/chat/nuevo',{method:'POST',body:fd,redirect:'follow'}).then(function(r){
    if(r.redirected){
      var match=r.url.match(/\/chat\/(\d+)/);
      if(match){chatLoadRooms();setTimeout(function(){chatOpenRoom(parseInt(match[1]));},500);return;}
    }
    chatLoadRooms();
  }).catch(function(){chatLoadRooms();});
}

function chatOpenRoom(roomId){
  _chatRoomId = roomId;
  _chatLastMsgId = 0;
  localStorage.setItem('evore_last_chat', roomId);
  chatRenderTabs();
  document.getElementById('chatInput').style.display = '';
  document.getElementById('chatMsgs').innerHTML = '<div style="padding:20px;text-align:center;color:var(--text2);font-size:.82rem">Cargando...</div>';
  chatPollMessages();
  if(_chatPollTimer) clearInterval(_chatPollTimer);
  _chatPollTimer = setInterval(chatPollMessages, 3000);
  setTimeout(function(){ document.getElementById('chatMsgInput').focus(); }, 100);
  // Mark as read — hit the room page to trigger read marking + update badge
  fetch('/chat/'+roomId, {headers:{'X-Requested-With':'XMLHttpRequest'}}).catch(function(){});
  setTimeout(function(){
    fetch('/api/chat/unread').then(function(r){return r.json()}).then(function(d){
      var badge=document.getElementById('chatBadge');
      if(badge){if(d.count>0){badge.textContent=d.count;badge.classList.remove('hide')}else{badge.classList.add('hide')}}
      var mb=document.getElementById('mnavChatBadge');
      if(mb){if(d.count>0){mb.textContent=d.count;mb.classList.remove('hide')}else{mb.classList.add('hide')}}
    }).catch(function(){});
  }, 500);
}

function chatPollMessages(){
  if(!_chatRoomId) return;
  fetch('/api/chat/'+_chatRoomId+'/mensajes?after='+_chatLastMsgId)
    .then(r => r.json())
    .then(data => {
      if(!data.messages) return;
      var container = document.getElementById('chatMsgs');
      if(_chatLastMsgId === 0) container.innerHTML = '';
      data.messages.forEach(function(m){
        if(m.id <= _chatLastMsgId) return;
        _chatLastMsgId = m.id;
        var div = document.createElement('div');
        div.style = 'display:flex;' + (m.is_mine ? 'justify-content:flex-end' : 'justify-content:flex-start');
        var bubble = document.createElement('div');
        bubble.style = 'max-width:80%;padding:8px 12px;border-radius:' +
          (m.is_mine ? '16px 16px 4px 16px' : '16px 16px 16px 4px') + ';font-size:.85rem;' +
          (m.tipo === 'sistema' ? 'background:transparent;color:var(--text2);font-size:.72rem;text-align:center;max-width:100%;font-style:italic' :
           m.is_mine ? 'background:var(--ac);color:#fff' : 'background:var(--surface);color:var(--text);border:1px solid var(--border)');
        var html = '';
        if(m.tipo !== 'sistema' && !m.is_mine)
          html += '<div style="font-size:.68rem;font-weight:600;color:var(--ac);margin-bottom:2px">'+m.user_name+'</div>';
        html += m.contenido;
        html += '<div style="font-size:.6rem;margin-top:3px;'+(m.is_mine?'color:rgba(255,255,255,.6);text-align:right':'color:var(--text2)')+'">'+m.creado_en+'</div>';
        bubble.innerHTML = html;
        div.appendChild(bubble);
        container.appendChild(div);
        div.style.animation='msgIn .2s ease';
      });
      container.scrollTop = container.scrollHeight;
    }).catch(function(){});
}

function chatSend(e){
  e.preventDefault();
  var input = document.getElementById('chatMsgInput');
  var text = input.value.trim();
  if(!text || !_chatRoomId) return;
  input.value = '';
  // Send to server first, then poll will bring it back — no optimistic double
  var fd = new FormData();
  fd.append('contenido', text);
  fd.append('_csrf_token', _csrfToken);
  fetch('/chat/'+_chatRoomId+'/enviar', {method:'POST', body:fd, headers:{'X-Requested-With':'XMLHttpRequest'}})
    .then(function(){ chatPollMessages(); })
    .catch(function(){});
}



// Poll unread count + show notification toast on new messages
var _lastChatCount=0,_lastChatMsgId=0;
function pollChatUnread(){
  fetch('/api/chat/unread').then(function(r){return r.json()}).then(function(d){
    var badge=document.getElementById('chatBadge');
    if(badge){if(d.count>0){badge.textContent=d.count;badge.classList.remove('hide')}else{badge.classList.add('hide')}}
    var mb=document.getElementById('mnavChatBadge');
    if(mb){if(d.count>0){mb.textContent=d.count;mb.classList.remove('hide')}else{mb.classList.add('hide')}}
    // Store per-room unread and refresh tabs
    if(d.per_room){_chatUnreadPerRoom=d.per_room;if(_chatOpen)chatRenderTabs()}
    // Show notification toast if new message arrived and chat panel is closed
    if(d.count>_lastChatCount && d.last && d.last.id!==_lastChatMsgId && !_chatOpen){
      _lastChatMsgId=d.last.id;
      showChatNotif(d.last);
    }
    _lastChatCount=d.count;
  }).catch(function(){});
}
function playChatSound(){
  try{
    var ctx=new (window.AudioContext||window.webkitAudioContext)();
    var osc=ctx.createOscillator();var gain=ctx.createGain();
    osc.connect(gain);gain.connect(ctx.destination);
    osc.frequency.setValueAtTime(880,ctx.currentTime);
    osc.frequency.setValueAtTime(1100,ctx.currentTime+.08);
    gain.gain.setValueAtTime(.15,ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(.001,ctx.currentTime+.3);
    osc.start(ctx.currentTime);osc.stop(ctx.currentTime+.3);
  }catch(e){}
}
function showChatNotif(msg){
  playChatSound();
  var existing=document.getElementById('chatNotifToast');
  if(existing) existing.remove();
  var div=document.createElement('div');
  div.id='chatNotifToast';
  div.style.cssText='position:fixed;bottom:24px;right:24px;z-index:1090;background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:.85rem 1rem;box-shadow:0 12px 40px rgba(0,0,0,.12);display:flex;align-items:center;gap:.75rem;max-width:340px;cursor:pointer;animation:chatNotifIn .3s ease';
  div.innerHTML='<div style="width:36px;height:36px;border-radius:10px;background:var(--ac);display:flex;align-items:center;justify-content:center;color:#fff;font-size:.85rem;flex-shrink:0"><i class="bi bi-chat-dots-fill"></i></div>'
    +'<div style="flex:1;min-width:0"><div style="font-weight:600;font-size:.82rem;color:var(--text)">'+msg.user+'</div><div style="font-size:.75rem;color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+msg.text+'</div></div>'
    +'<button onclick="event.stopPropagation();this.parentElement.remove()" style="background:none;border:none;color:var(--text2);cursor:pointer;font-size:.9rem;padding:2px;line-height:1">&times;</button>';
  div.onclick=function(){toggleChatPanel();if(msg.room_id)chatOpenRoom(msg.room_id);this.remove()};
  document.body.appendChild(div);
  setTimeout(function(){var t=document.getElementById('chatNotifToast');if(t){t.style.transition='opacity .4s';t.style.opacity='0';setTimeout(function(){if(t.parentNode)t.remove()},400)}},8000);
}
pollChatUnread();
setInterval(pollChatUnread, 10000);

// ── Block from line 2643 ──
// ── PWA Install button in header ──
var _deferredInstall=null;
// Hide if already in standalone mode (installed PWA)
if(window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone){
  var _b=document.getElementById('pwaInstallBtn'); if(_b) _b.style.display='none';
}
window.addEventListener('beforeinstallprompt',function(e){
  e.preventDefault(); _deferredInstall=e;
  // Only show if NOT already installed
  if(!window.matchMedia('(display-mode: standalone)').matches && !window.navigator.standalone){
    var btn=document.getElementById('pwaInstallBtn');
    if(btn) btn.style.display='';
  }
});
function pwaInstall(){
  if(_deferredInstall){_deferredInstall.prompt();_deferredInstall.userChoice.then(function(){
    document.getElementById('pwaInstallBtn').style.display='none';_deferredInstall=null;
  });}
}

// ── Global keyboard shortcuts ──
document.addEventListener('keydown', function(e) {
  // Don't trigger in inputs/textareas
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT' || e.target.isContentEditable) return;
  // Ctrl/Cmd + K = global search (already exists as diagBtn)
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    var searchBtn = document.getElementById('diagBtn');
    if (searchBtn) searchBtn.click();
    return;
  }
  // Single key shortcuts (no modifier)
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  switch(e.key) {
    case 'g': // Go home
      if(!e.shiftKey) window.location.href = '/';
      break;
    case '?': // Show shortcuts help
      var helpHtml = '<div style="position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:99999;display:flex;align-items:center;justify-content:center" onclick="this.remove()">'
        + '<div style="background:var(--surface);border-radius:12px;padding:2rem;max-width:400px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.3)" onclick="event.stopPropagation()">'
        + '<h5 style="margin:0 0 1rem"><i class="bi bi-keyboard me-2"></i>Atajos de teclado</h5>'
        + '<table style="width:100%;font-size:.85rem"><tbody>'
        + '<tr><td style="padding:4px 8px"><kbd style="background:var(--surface2);padding:2px 8px;border-radius:4px;font-size:.8rem">Ctrl+K</kbd></td><td>Busqueda global</td></tr>'
        + '<tr><td style="padding:4px 8px"><kbd style="background:var(--surface2);padding:2px 8px;border-radius:4px;font-size:.8rem">G</kbd></td><td>Ir al dashboard</td></tr>'
        + '<tr><td style="padding:4px 8px"><kbd style="background:var(--surface2);padding:2px 8px;border-radius:4px;font-size:.8rem">?</kbd></td><td>Mostrar atajos</td></tr>'
        + '<tr><td style="padding:4px 8px"><kbd style="background:var(--surface2);padding:2px 8px;border-radius:4px;font-size:.8rem">Esc</kbd></td><td>Cerrar panel/modal</td></tr>'
        + '</tbody></table>'
        + '<div style="margin-top:1rem;text-align:right"><button onclick="this.closest(\'[style]\').remove()" class="btn btn-sm btn-outline-secondary">Cerrar</button></div>'
        + '</div></div>';
      document.body.insertAdjacentHTML('beforeend', helpHtml);
      break;
  }
});

// ── Block from line 2698 ──
// ── Live notification badge polling (every 30s) ──
(function(){
  var btn = document.getElementById('notifBtn');
  if(!btn) return;
  var badge = btn.querySelector('.notif-badge');
  var lastCount = badge ? (parseInt(badge.textContent) || 0) : 0;

  function ensureBadge(){
    if(!badge){
      badge = document.createElement('span');
      badge.className = 'notif-badge hide';
      btn.appendChild(badge);
    }
  }

  function poll(){
    fetch('/api/notif-count').then(function(r){ return r.json(); }).then(function(d){
      var c = d.count || 0;
      ensureBadge();
      if(c > 0){
        badge.textContent = c < 10 ? c : '9+';
        badge.classList.remove('hide');
      } else {
        badge.classList.add('hide');
      }
      if(c > lastCount && c > 0){
        badge.classList.add('notif-pulse');
        setTimeout(function(){ badge.classList.remove('notif-pulse'); }, 500);
      }
      lastCount = c;
    }).catch(function(){});
  }
  setInterval(poll, 30000);
})();

// ── Block from line 2796 ──
// Auto-link form-text helpers to their inputs via aria-describedby
document.querySelectorAll('.form-text').forEach(function(el,i){
  var input = el.previousElementSibling || el.parentElement.querySelector('input,select,textarea');
  if(input && !input.getAttribute('aria-describedby')){
    var id = 'ft_' + i;
    el.id = id;
    input.setAttribute('aria-describedby', id);
  }
});
// Sync aria-invalid with Bootstrap .is-invalid class
new MutationObserver(function(mutations){
  mutations.forEach(function(m){
    if(m.type==='attributes'&&m.attributeName==='class'){
      var el=m.target;
      if(el.classList.contains('is-invalid')) el.setAttribute('aria-invalid','true');
      else el.removeAttribute('aria-invalid');
    }
  });
}).observe(document.body,{attributes:true,subtree:true,attributeFilter:['class']});


// ── Anti-double-click: disable submit buttons on form submit ──
document.addEventListener('submit',function(e){
  var form=e.target;
  if(form.tagName!=='FORM') return;
  if(form.method.toUpperCase()==='GET') return;
  var btns=form.querySelectorAll('button[type="submit"],input[type="submit"]');
  btns.forEach(function(btn){
    if(btn.disabled) return;
    btn.disabled=true;
    btn.dataset.originalText=btn.innerHTML;
    btn.innerHTML='<span class="spinner-border spinner-border-sm me-1" role="status"></span>Procesando...';
    setTimeout(function(){btn.disabled=false;btn.innerHTML=btn.dataset.originalText||'Enviar';},8000);
  });
});

// ── PostHog: identify user + custom events ──
(function(){
  if(typeof posthog==='undefined') return;
  // Identify logged-in user (data attributes set in base.html)
  var b=document.body;
  var uid=b.dataset.userId, uemail=b.dataset.userEmail, urol=b.dataset.userRol;
  if(uid) posthog.identify(uid,{email:uemail||'',rol:urol||''});
  // Track key form submissions
  document.addEventListener('submit',function(e){
    var f=e.target, a=f.getAttribute('action')||'';
    if(a.indexOf('/venta/nueva')!==-1||a.indexOf('/ventas/nueva')!==-1) posthog.capture('venta_created');
    if(a.indexOf('/clientes/nuevo')!==-1) posthog.capture('cliente_created');
    if(a.indexOf('/foro/nueva')!==-1) posthog.capture('foro_published');
    if(a.indexOf('/planes/suscribir')!==-1) posthog.capture('suscripcion_pro');
    if(a.indexOf('/contacto')!==-1&&a.indexOf('/contactos')===-1) posthog.capture('landing_contact');
    if(a.indexOf('/login')!==-1) posthog.capture('login_attempt');
  });
})();
