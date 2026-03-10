import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
from PyQt6.QtWidgets import QSizePolicy

class ResponsiveChart(FigureCanvas):
    def __init__(self, parent=None, width=5.0, height=4.0, dpi=100):
        # Premium dark theme base
        self.fig = Figure(figsize=(width, height), dpi=dpi, facecolor='#181c33')
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#181c33')
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(350) 
        self.updateGeometry()

    def clear(self):
        self.ax.clear()
        self.ax.set_facecolor('#181c33')
        
    def draw(self):
        try:
            # Increased bottom margin (0.22) to accommodate rotated machine labels
            # Increased top margin (0.90) for headroom
            self.fig.subplots_adjust(left=0.1, right=0.95, top=0.90, bottom=0.22)
            super().draw()
        except: pass

class ChartManager:
    @staticmethod
    def create_bar_chart_widget(data, title="", colors=None, orientation='vertical'):
        if not data:
            return ChartManager.create_empty_widget(title)
            
        canvas = ResponsiveChart()
        ax = canvas.ax
        
        labels = [str(k) for k in data.keys()]
        values = [float(v) for v in data.values()]
        
        # Headroom scaling
        if values and max(values) > 0:
            if orientation == 'vertical':
                ax.set_ylim(0, max(values) * 1.15)
            else:
                ax.set_xlim(0, max(values) * 1.2)
        else:
            if orientation == 'vertical': ax.set_ylim(0, 1)
            else: ax.set_xlim(0, 1)
        
        # Adaptive bar width: wider bars for fewer items
        bar_width = 0.6 if len(labels) > 3 else 0.4
        
        if orientation == 'vertical':
            bars = ax.bar(labels, values, color=colors or '#38bdf8', width=bar_width, zorder=3, alpha=0.9)
            # Reduced rotation slightly (from 30 to 20) and added padding
            ax.tick_params(axis='x', rotation=20, labelsize=8, colors='#94a3b8', pad=5)
            ax.set_ylabel("Value", color='#94a3b8', fontsize=8, fontweight='bold', labelpad=10)
            for bar in bars:
                h = bar.get_height()
                ax.annotate(f'{int(h):,}', xy=(bar.get_x() + bar.get_width() / 2, h),
                            xytext=(0, 8), textcoords="offset points",
                            ha='center', va='bottom', color='white', fontsize=9, fontweight='900')
        else:
            y_pos = np.arange(len(labels))
            # Expand left margin for horizontal labels
            canvas.fig.subplots_adjust(left=0.25)
            bars = ax.barh(y_pos, values, color=colors or '#10b981', height=bar_width, zorder=3, alpha=0.9)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels)
            ax.tick_params(axis='y', labelsize=8, colors='#94a3b8')
            ax.set_xlabel("Value", color='#94a3b8', fontsize=8, fontweight='bold')
            for bar in bars:
                w = bar.get_width()
                ax.annotate(f'{int(w):,}', xy=(w, bar.get_y() + bar.get_height() / 2),
                            xytext=(10, 0), textcoords="offset points",
                            ha='left', va='center', color='white', fontsize=9, fontweight='900')

        ax.tick_params(axis='both', colors='#94a3b8', labelsize=8)
        ax.grid(axis='y' if orientation == 'vertical' else 'x', linestyle='--', alpha=0.05, zorder=0)
        for spine in ax.spines.values(): spine.set_visible(False)
            
        try: canvas.fig.tight_layout(pad=2.0)
        except: pass
        canvas.draw()
        return canvas

    @staticmethod
    def create_empty_widget(title):
        canvas = ResponsiveChart()
        ax = canvas.ax
        ax.text(0.5, 0.5, "NO DATA IN SELECTION", ha='center', va='center', color='#475569', fontsize=10, fontweight='800')
        ax.axis('off')
        canvas.draw()
        return canvas

    @staticmethod
    def create_grouped_bar_widget(data_groups, labels, title="", category_labels=None):
        if not data_groups or not any(data_groups) or not category_labels:
             return ChartManager.create_empty_widget(title)

        canvas = ResponsiveChart()
        ax = canvas.ax
        x = np.arange(len(category_labels))
        width = 0.35
        colors = ['#6366f1', '#fbbf24', '#10b981', '#f43f5e']
        
        # Max headroom
        max_val = 0
        for group in data_groups:
            if group and len(group) > 0:
                max_val = max(max_val, max(group))
        
        if max_val > 0:
            ax.set_ylim(0, max_val * 1.25)
        else:
            ax.set_ylim(0, 1)
        
        for i, (group_data, label) in enumerate(zip(data_groups, labels)):
            offset = (i - len(data_groups)/2 + 0.5) * width
            bars = ax.bar(x + offset, group_data, width, label=label, color=colors[i % len(colors)], zorder=3, alpha=0.8)
            for bar in bars:
                h = bar.get_height()
                if h > 0:
                    ax.annotate(f'{int(h):,}', xy=(bar.get_x() + bar.get_width() / 2, h),
                                xytext=(0, 5), textcoords="offset points",
                                ha='center', va='bottom', color='white', fontsize=8, fontweight='bold')

        ax.set_xticks(x)
        # Consistent rotation with bar charts
        ax.set_xticklabels(category_labels, rotation=20)
        ax.tick_params(axis='both', labelsize=8, colors='#94a3b8', pad=5)
        ax.legend(frameon=False, fontsize=8, loc='upper right', labelcolor='white')
        
        ax.grid(axis='y', linestyle='--', alpha=0.05, zorder=0)
        for spine in ax.spines.values(): spine.set_visible(False)
            
        try: canvas.fig.tight_layout(pad=2.5)
        except: pass
        canvas.draw()
        return canvas

    @staticmethod
    def create_pie_chart_widget(data, title=""):
        if not data or sum(data.values()) == 0:
            return ChartManager.create_empty_widget(title)

        canvas = ResponsiveChart()
        ax = canvas.ax
        # Ensure donut filling and clear labels
        labels = list(data.keys())
        values = [float(v) for v in data.values()]
        colors = ['#38bdf8', '#fbbf24', '#34d399', '#f43f5e', '#a78bfa']
        
        try:
            wedges, texts, autotexts = ax.pie(values, labels=labels, autopct='%1.1f%%', 
                   startangle=140, colors=colors,
                   wedgeprops={'width': 0.45, 'edgecolor': '#181c33', 'linewidth': 2},
                   textprops={'color': '#f1f5f9', 'fontsize': 9, 'fontweight': 'bold'})
            plt.setp(autotexts, size=9, weight="900", color="white")
        except: pass
        
        try: canvas.fig.tight_layout(pad=1.5)
        except: pass
        canvas.draw()
        return canvas

    @staticmethod
    def create_scatter_plot_widget(data, title="", x_key="mcTime", y_key="revPerHour", z_key=None):
        if not data: return ChartManager.create_empty_widget(title)

        canvas = ResponsiveChart()
        ax = canvas.ax
        x = [float(d[x_key]) for d in data]
        y = [float(d[y_key]) for d in data]
        
        # Headroom
        if y and max(y) > 0: 
            ax.set_ylim(min(y)*0.8, max(y)*1.3)
        else:
            ax.set_ylim(0, 1)
        
        # Professional bubble scaling
        sizes = [min(1200, max(100, float(d[z_key])/80)) for d in data] if z_key else 200
        
        ax.scatter(x, y, s=sizes, color='#6366f1', alpha=0.6, zorder=3, edgecolors='white', linewidth=1.5)
        for i, d in enumerate(data):
            ax.annotate(d.get('pjc', ''), (x[i], y[i]), xytext=(8, 8), textcoords='offset points', 
                        color='white', fontsize=8, fontweight='900')

        ax.set_xlabel("Operational Duration (Hrs)", color='#94a3b8', fontsize=8, fontweight='bold')
        ax.set_ylabel("Production Velocity (MUR/Hr)", color='#94a3b8', fontsize=8, fontweight='bold')
        ax.tick_params(axis='both', colors='#94a3b8', labelsize=8)
        ax.grid(linestyle='--', alpha=0.05, zorder=0)
        for spine in ax.spines.values(): spine.set_visible(False)
            
        try: canvas.fig.tight_layout(pad=3.0)
        except: pass
        canvas.draw()
        return canvas

    @staticmethod
    def create_area_chart_widget(data, title="", color='#6366f1'):
        if not data: return ChartManager.create_empty_widget(title)
            
        canvas = ResponsiveChart()
        ax = canvas.ax
        labels = [str(k) for k in data.keys()]
        values = [float(v) for v in data.values()]
        x = np.arange(len(labels))
        
        # Headroom for labels
        if values and max(values) > 0:
            ax.set_ylim(0, max(values) * 1.35)
            # If only one data point, center it
            if len(values) == 1: ax.set_xlim(-0.5, 0.5)
        else:
            ax.set_ylim(0, 1)

        # Premium Glow Effect Gradient-like Area
        ax.fill_between(x, values, color=color, alpha=0.15, zorder=1)
        ax.plot(x, values, color=color, linewidth=4, marker='o', markersize=10, 
                zorder=3, markerfacecolor='white', markeredgewidth=3, markeredgecolor=color)
        
        for i, val in enumerate(values):
            ax.annotate(f'MUR {int(val):,}', xy=(x[i], val), xytext=(0, 15), textcoords="offset points",
                        ha='center', va='bottom', color='white', fontsize=10, fontweight='900',
                        bbox=dict(boxstyle='round,pad=0.4', fc='#1e1e3f', alpha=0.8, ec=color, lw=1))

        # Maximize trend line space
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=0)
        ax.tick_params(axis='both', labelsize=8, colors='#94a3b8')
        ax.set_ylabel("Revenue Performance Index", color='#94a3b8', fontsize=8, fontweight='bold')
        ax.grid(axis='y', linestyle='--', alpha=0.08, zorder=0)
        for spine in ax.spines.values(): spine.set_visible(False)
            
        try: canvas.fig.tight_layout(pad=3.0)
        except: pass
        canvas.draw()
        return canvas
