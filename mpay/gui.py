import tkinter as tk
import tkinter.ttk as ttk


class DfGUI(tk.Frame):
    """Generic pandas dataframe display."""

    def __init__(self, parent, df):
        super().__init__(parent)
        self.parent = parent
        self.parent.title("Mpay results")
        self.df = df
        self.create_widgets()

    def create_widgets(self):
        self.columns: list[str] = list(self.df)
        self.trv = ttk.Treeview(self.parent, show="headings", columns=self.columns)

        self.vsb = ttk.Scrollbar(self.parent, orient="vertical", command=self.trv.yview)
        self.trv.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.trv.pack(fill=tk.BOTH, side=tk.LEFT, expand=True)

        self.fill_trv()

    def fill_trv(self):
        for col in self.columns:
            self.trv.column(col, anchor=tk.CENTER)
            self.trv.heading(col, text=col)

        for _, row in self.df.iterrows():
            self.trv.insert("", "end", iid=row.id, values=row.tolist())


class HistoryDfGUI(DfGUI):
    def __init__(self, parent, df, user_me):
        self.user_me = user_me
        super().__init__(parent, df)

    def fill_trv(self):
        for col in self.columns:
            self.trv.column(col, anchor=tk.CENTER)
            self.trv.heading(col, text=col)

        for _, row in self.df.iterrows():
            self.trv.insert("", "end", iid=row.id, values=row.tolist(),
                            tags="incoming" if row["to"] == self.user_me else "outgoing")

        self.trv.tag_configure("outgoing", background="#ffb3b3")
        self.trv.tag_configure("incoming", background="#b3ffb3")


def show_df(df, view=DfGUI, *args):
    root = tk.Tk()
    app = view(root, df, *args)
    app.mainloop()
