/**
 * Haru Roadmap Canvas v4 — layer-based horizontal branch graph.
 */
class RoadmapCanvas {
    constructor(canvas, scrollContainer) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.scrollContainer = scrollContainer;
        this.roadmapData = null;
        this.graph = null;
        this.selectedTaskId = null;
        this.currentFocusTaskId = null;
        this.lang = 'en';
        this.hoveredNode = null;
        this.nodes = [];
        this.edges = [];
        this.phases = [];
        this.dpr = window.devicePixelRatio || 1;
        this._pulsePhase = 0;
        this._animFrame = null;

        this.NODE_W = 196;
        this.NODE_H = 64;
        this.FORK_SIZE = 34;
        this.MERGE_SIZE = 28;
        this.PAD = 28;

        this._onClick = this._onClick.bind(this);
        this._onMove = this._onMove.bind(this);
        this._onLeave = this._onLeave.bind(this);
        this._onResize = this._onResize.bind(this);

        canvas.addEventListener('click', this._onClick);
        canvas.addEventListener('mousemove', this._onMove);
        canvas.addEventListener('mouseleave', this._onLeave);
        window.addEventListener('resize', this._onResize);
    }

    destroy() {
        this.canvas.removeEventListener('click', this._onClick);
        this.canvas.removeEventListener('mousemove', this._onMove);
        this.canvas.removeEventListener('mouseleave', this._onLeave);
        window.removeEventListener('resize', this._onResize);
        this._stopPulse();
    }

    _stopPulse() {
        if (this._animFrame) {
            cancelAnimationFrame(this._animFrame);
            this._animFrame = null;
        }
    }

    _startPulse() {
        this._stopPulse();
        if (!this.currentFocusTaskId) return;
        const tick = () => {
            this._pulsePhase = (this._pulsePhase + 0.06) % (Math.PI * 2);
            this.render();
            this._animFrame = requestAnimationFrame(tick);
        };
        this._animFrame = requestAnimationFrame(tick);
    }

    setData(roadmapData, selectedTaskId, lang, currentFocusTaskId) {
        this.roadmapData = roadmapData;
        this.graph = roadmapData?.graph || null;
        this.selectedTaskId = selectedTaskId;
        this.currentFocusTaskId = currentFocusTaskId
            || roadmapData?.next_tasks?.[0]?.id
            || null;
        this.lang = lang || 'en';
        this._buildNodes();
        this.render();
        this._startPulse();
    }

    scrollToCurrentFocus() {
        if (!this.currentFocusTaskId) return;
        const node = this.nodes.find((n) => n.task_id === this.currentFocusTaskId);
        if (!node || !this.scrollContainer) return;
        this.scrollContainer.scrollTo({
            left: Math.max(0, node.x - this.scrollContainer.clientWidth / 2 + node.w / 2),
            behavior: 'smooth',
        });
    }

    scrollToPhase(phaseId) {
        const phaseNodes = this.nodes.filter((n) => n.phase_id === phaseId);
        if (!phaseNodes.length || !this.scrollContainer) return;
        const minX = Math.min(...phaseNodes.map((n) => n.x));
        this.scrollContainer.scrollTo({ left: Math.max(0, minX - 48), behavior: 'smooth' });
    }

    _buildNodes() {
        this.nodes = [];
        this.edges = this.graph?.edges || [];
        this.phases = this.graph?.phases || this.roadmapData?.phases || [];
        if (!this.graph?.nodes) return;

        for (const gn of this.graph.nodes) {
            let w = this.NODE_W;
            let h = this.NODE_H;
            if (gn.node_type === 'fork') { w = h = this.FORK_SIZE; }
            if (gn.node_type === 'merge') { w = h = this.MERGE_SIZE; }
            const x = gn.x || 0;
            const y = gn.y || 0;
            this.nodes.push({ ...gn, x, y, w, h, cx: x + w / 2, cy: y + h / 2 });
        }

        const dims = this.graph.dimensions || { width: 1200, height: 400 };
        this.logicalW = dims.width;
        this.logicalH = dims.height;
    }

    _isDark() {
        return document.documentElement.classList.contains('dark')
            || window.matchMedia('(prefers-color-scheme: dark)').matches;
    }

    _labels() {
        const trans = (window.uiTranslations && window.uiTranslations[this.lang]) || {};
        return {
            done: trans.roadmapStateDone || 'Done',
            active: trans.roadmapStateActive || 'Active',
            here: trans.roadmapStateHere || 'You are here',
            locked: trans.roadmapStateLocked || 'Locked',
            alt: trans.roadmapStateAlt || 'Alt path',
            fork: trans.roadmapStateFork || 'Branch',
            merge: trans.roadmapStateMerge || 'Merge',
        };
    }

    _palette() {
        return {
            bg0: '#f3f3f9',
            bg1: '#ededf3',
            grid: 'rgba(94, 75, 179, 0.06)',
            phase: 'rgba(94, 75, 179, 0.08)',
            phaseBorder: 'rgba(200, 242, 80, 0.35)',
            text: '#191c20',
            sub: '#484552',
            edge: 'rgba(121, 117, 131, 0.35)',
            edgeActive: '#5e4bb3',
            edgeAlt: 'rgba(243, 181, 211, 0.6)',
            edgeMerge: 'rgba(94, 75, 179, 0.35)',
            glow: 'rgba(200, 242, 80, 0.4)',
            completed: {
                fill: '#c8f250', stroke: '#4f6600', text: '#161f00',
            },
            available: {
                fill: '#7764ce', stroke: '#5e4bb3', text: '#ffffff',
            },
            locked: {
                fill: '#e2e2e8', stroke: '#c9c4d4', text: '#797583',
            },
            alternative: {
                fill: '#f3b5d3', stroke: '#f3b5d3', text: '#340d24',
            },
            selected_path: {
                fill: '#ffd8e9', stroke: '#5e4bb3', text: '#340d24',
            },
            fork: {
                fill: '#c8f250', stroke: '#5e4bb3', text: '#161f00',
            },
            merge: {
                fill: '#b89ae8', stroke: '#c1ff72', text: '#2d1b4e',
            },
        };
    }

    _stateStyle(state, c) {
        if (state === 'completed') return c.completed;
        if (state === 'locked') return c.locked;
        if (state === 'alternative') return c.alternative;
        if (state === 'selected_path') return c.selected_path;
        return c.available;
    }

    _resizeCanvas() {
        const w = this.logicalW || 1200;
        const h = this.logicalH || 400;
        this.canvas.style.width = `${w}px`;
        this.canvas.style.height = `${h}px`;
        this.canvas.width = Math.floor(w * this.dpr);
        this.canvas.height = Math.floor(h * this.dpr);
        this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    }

    _roundRect(x, y, w, h, r) {
        const ctx = this.ctx;
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
    }

    _truncate(text, maxW) {
        if (this.ctx.measureText(text).width <= maxW) return text;
        let t = text;
        while (t.length > 1 && this.ctx.measureText(t + '…').width > maxW) t = t.slice(0, -1);
        return t + '…';
    }

    _drawBackground(c) {
        const ctx = this.ctx;
        const w = this.logicalW;
        const h = this.logicalH;
        const grd = ctx.createLinearGradient(0, 0, w, 0);
        grd.addColorStop(0, c.bg0);
        grd.addColorStop(1, c.bg1);
        ctx.fillStyle = grd;
        ctx.fillRect(0, 0, w, h);

        ctx.fillStyle = c.grid;
        for (let x = 0; x < w; x += 24) {
            for (let y = 0; y < h; y += 24) {
                ctx.fillRect(x, y, 1, 1);
            }
        }
    }

    _phaseBands(c) {
        const bands = [];
        for (const phase of this.phases) {
            const pn = this.nodes.filter((n) => n.phase_id === phase.id);
            if (!pn.length) continue;
            const x0 = Math.min(...pn.map((n) => n.x)) - 16;
            const x1 = Math.max(...pn.map((n) => n.x + n.w)) + 16;
            bands.push({ phase, x0, x1 });
        }
        return bands;
    }

    _drawPhaseBands(c) {
        const ctx = this.ctx;
        const y0 = this.PAD;
        const y1 = this.logicalH - this.PAD - 28;
        for (const band of this._phaseBands(c)) {
            const w = band.x1 - band.x0;
            ctx.fillStyle = c.phase;
            this._roundRect(band.x0, y0, w, y1 - y0, 14);
            ctx.fill();
            ctx.strokeStyle = c.phaseBorder;
            ctx.lineWidth = 0;

            ctx.font = 'bold 10px system-ui,sans-serif';
            ctx.fillStyle = c.edgeActive;
            ctx.textAlign = 'center';
            ctx.fillText(this._truncate(band.phase.title, w - 20), band.x0 + w / 2, y0 + 14);
        }
    }

    _nodeById(id) {
        return this.nodes.find((n) => n.id === id);
    }

    _drawEdges(c) {
        const ctx = this.ctx;
        for (const edge of this.edges) {
            const a = this._nodeById(edge.from);
            const b = this._nodeById(edge.to);
            if (!a || !b) continue;

            const active = edge.active !== false;
            let color = active ? c.edgeActive : c.edge;
            if (edge.type === 'branch' && !active) color = c.edgeAlt;
            if (edge.type === 'merge') color = c.edgeMerge;

            ctx.strokeStyle = color;
            ctx.lineWidth = edge.type === 'flow' && active ? 2.4 : 1.6;
            ctx.setLineDash((!active || edge.type === 'merge') ? [5, 4] : []);

            const x1 = a.x + a.w;
            const y1 = a.cy;
            const x2 = b.x;
            const y2 = b.cy;

            ctx.beginPath();
            ctx.moveTo(x1, y1);
            const mx = (x1 + x2) / 2;
            ctx.bezierCurveTo(mx, y1, mx, y2, x2, y2);
            ctx.stroke();
        }
        ctx.setLineDash([]);
    }

    _drawFork(node, c) {
        const ctx = this.ctx;
        const st = c.fork;
        const s = node.w;
        ctx.save();
        ctx.translate(node.cx, node.cy);
        ctx.rotate(Math.PI / 4);
        ctx.fillStyle = st.fill;
        ctx.strokeStyle = st.stroke;
        ctx.lineWidth = 2;
        ctx.fillRect(-s / 2, -s / 2, s, s);
        ctx.strokeRect(-s / 2, -s / 2, s, s);
        ctx.restore();
    }

    _drawMerge(node, c) {
        const ctx = this.ctx;
        const st = c.merge;
        const r = node.w / 2;
        ctx.beginPath();
        ctx.arc(node.cx, node.cy, r, 0, Math.PI * 2);
        ctx.fillStyle = st.fill;
        ctx.fill();
        ctx.strokeStyle = st.stroke;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.font = 'bold 10px system-ui';
        ctx.fillStyle = st.text;
        ctx.textAlign = 'center';
        ctx.fillText('+', node.cx, node.cy + 4);
    }

    _drawCurrentFocusPulse(node, c) {
        if (!this.currentFocusTaskId || node.task_id !== this.currentFocusTaskId) return;
        if (node.state === 'completed' || node.state === 'locked') return;
        const ctx = this.ctx;
        const pulse = 0.45 + 0.55 * Math.sin(this._pulsePhase);
        const pad = 6 + pulse * 5;
        const r = node.h / 2 + pad;
        const cx = node.x + node.w / 2;
        const cy = node.y + node.h / 2;

        ctx.save();
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(200, 242, 80, ${0.35 + pulse * 0.45})`;
        ctx.lineWidth = 2.5 + pulse * 2;
        ctx.shadowColor = c.glow;
        ctx.shadowBlur = 8 + pulse * 10;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(cx, cy, r + 4 + pulse * 3, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(94, 75, 179, ${0.15 + pulse * 0.25})`;
        ctx.lineWidth = 1.5;
        ctx.shadowBlur = 0;
        ctx.stroke();
        ctx.restore();
    }

    _drawTaskCard(node, c, labels, isSel, isHover) {
        const ctx = this.ctx;
        const isCurrent = node.task_id === this.currentFocusTaskId
            && node.state !== 'completed'
            && node.state !== 'locked';
        const st = this._stateStyle(node.state, c);
        const r = node.h / 2;

        if (isSel || isHover) {
            ctx.shadowColor = c.glow;
            ctx.shadowBlur = isSel ? 14 : 7;
        }

        ctx.fillStyle = st.fill;
        this._roundRect(node.x, node.y, node.w, node.h, r);
        ctx.fill();
        ctx.shadowBlur = 0;

        const badge = node.state === 'completed' ? 'x'
            : node.state === 'locked' ? '-'
            : node.state === 'alternative' ? '~'
            : node.branch_point && !node.branch_point.selected ? '?' : '>';

        ctx.font = '10px "Noto Sans JP", sans-serif';
        ctx.fillStyle = st.text;
        ctx.textAlign = 'left';
        ctx.fillText(badge, node.x + 10, node.y + 18);

        ctx.font = 'bold 11px "Noto Sans JP", sans-serif';
        ctx.fillText(this._truncate(node.label || '', node.w - 24), node.x + 22, node.y + 19);

        ctx.font = '9px "Noto Sans JP", sans-serif';
        ctx.fillStyle = c.sub;
        let stateLbl = labels.active;
        if (node.state === 'completed') stateLbl = labels.done;
        else if (node.state === 'locked') stateLbl = labels.locked;
        else if (node.state === 'alternative') stateLbl = labels.alt;
        else if (isCurrent) stateLbl = labels.here || labels.active;
        ctx.fillText(stateLbl, node.x + 22, node.y + 36);
    }

    _drawNodes(c) {
        const labels = this._labels();
        for (const node of this.nodes) {
            const isCurrent = node.task_id === this.currentFocusTaskId
                && node.state !== 'completed'
                && node.state !== 'locked';
            if (isCurrent && node.node_type !== 'fork' && node.node_type !== 'merge') {
                this._drawCurrentFocusPulse(node, c);
            }
        }
        for (const node of this.nodes) {
            const isSel = node.task_id === this.selectedTaskId;
            const isHover = this.hoveredNode?.id === node.id;
            if (node.node_type === 'fork') this._drawFork(node, c);
            else if (node.node_type === 'merge') this._drawMerge(node, c);
            else this._drawTaskCard(node, c, labels, isSel, isHover);
        }
    }

    _drawLegend(c) {
        const labels = this._labels();
        const items = [
            { label: labels.done, style: c.completed },
            { label: labels.active, style: c.available },
            { label: labels.alt, style: c.alternative },
            { label: labels.merge, style: c.merge },
        ];
        let lx = this.PAD;
        const ly = this.logicalH - 16;
        this.ctx.font = '9px system-ui';
        items.forEach((item) => {
            this.ctx.fillStyle = item.style.fill;
            this.ctx.strokeStyle = item.style.stroke;
            this.ctx.lineWidth = 1;
            this._roundRect(lx, ly - 10, 11, 11, 2);
            this.ctx.fill();
            this.ctx.stroke();
            this.ctx.fillStyle = c.sub;
            this.ctx.textAlign = 'left';
            this.ctx.fillText(item.label, lx + 15, ly);
            lx += 76;
        });
    }

    render() {
        if (!this.graph) {
            this.logicalW = 800;
            this.logicalH = 320;
            this._resizeCanvas();
            const c = this._palette();
            this._drawBackground(c);
            return;
        }
        this._resizeCanvas();
        const c = this._palette();
        this._drawBackground(c);
        this._drawPhaseBands(c);
        this._drawEdges(c);
        this._drawNodes(c);
        this._drawLegend(c);
    }

    _clientToLogical(evt) {
        const rect = this.canvas.getBoundingClientRect();
        return {
            x: (evt.clientX - rect.left) * (this.logicalW / rect.width),
            y: (evt.clientY - rect.top) * (this.logicalH / rect.height),
        };
    }

    _hitTest(x, y) {
        return this.nodes.find((n) => {
            if (n.node_type === 'fork' || n.node_type === 'merge') {
                const dx = x - n.cx;
                const dy = y - n.cy;
                return dx * dx + dy * dy <= (n.w / 2 + 6) ** 2;
            }
            return x >= n.x && x <= n.x + n.w && y >= n.y && y <= n.y + n.h;
        });
    }

    _onClick(evt) {
        const { x, y } = this._clientToLogical(evt);
        const hit = this._hitTest(x, y);
        if (!hit) return;

        if (hit.node_type === 'branch_path' && hit.state === 'alternative' && hit.branch_id && hit.choice_id) {
            if (hit.branch_id === 'housing_route') return;
            window.selectBranchChoice?.(hit.branch_id, hit.choice_id);
            return;
        }

        const taskId = hit.task_id;
        if (taskId) window.selectRoadmapTask?.(taskId);
        else if (hit.node_type === 'fork' && hit.task_id) window.selectRoadmapTask?.(hit.task_id);
    }

    _onMove(evt) {
        const { x, y } = this._clientToLogical(evt);
        const hit = this._hitTest(x, y);
        const prev = this.hoveredNode;
        this.hoveredNode = hit || null;
        this.canvas.style.cursor = hit ? 'pointer' : 'grab';
        if (prev?.id !== hit?.id) this.render();
    }

    _onLeave() {
        if (this.hoveredNode) {
            this.hoveredNode = null;
            this.canvas.style.cursor = 'default';
            this.render();
        }
    }

    _onResize() {
        if (this.graph) this.render();
    }
}

window.RoadmapCanvas = RoadmapCanvas;
