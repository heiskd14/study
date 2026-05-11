import tkinter as tk
from tkinter import messagebox
import json
import random
import time
import os

def load_questions(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def save_scores(record):
    file = "scores.json"
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = []
    data.append(record)
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def float_safe(val):
    try:
        return float(str(val).strip())
    except:
        return str(val).strip()

class KDCBTApp:
    def __init__(self, master):
        self.master = master
        self.master.title("KD CBT Examination")
        self.master.geometry("1280x760")
        self.master.configure(bg="white")
        self.subject_files = {
            "English": "english.json",
            "Mathematics": "maths.json",
            "General Paper": "general.json"
        }
        self.subject_questions = {}
        self.subject_answers = {}
        self.current_question = 0
        self.student_info = {}
        self.exam_time = 3600
        self.start_time = None
        self.selected_subject = None
        self.submitted = False
        self.number_buttons = []
        self.calc_window = None
        self.master.bind("<Left>", lambda e: self.go_prev())
        self.master.bind("<Right>", lambda e: self.go_next())
        for key, idx in zip(['a','b','c','d'], range(4)):
            self.master.bind(key, lambda e, i=idx: self.keyboard_select(i))
            self.master.bind(key.upper(), lambda e, i=idx: self.keyboard_select(i))
        self.master.bind("s", lambda e: self.confirm_submit())
        self.show_registration()

    def keyboard_select(self, idx):
        if self.submitted:
            return
        state_ans = self.subject_answers[self.selected_subject]
        if idx < len(state_ans):
            state_ans[self.current_question] = idx
            self.show_exam_interface()

    def show_registration(self):
        self.submitted = False
        self.current_question = 0
        self.start_time = None
        self.subject_questions = {}
        self.subject_answers = {}
        self.number_buttons = []
        self.clear()
        frame = tk.Frame(self.master,bg="white")
        frame.place(relx=0,rely=0,relwidth=1,relheight=1)
        tk.Label(frame,text="KD CBT Registration",font=("Segoe UI",28,"bold"),fg="#137a13",bg="white").pack(pady=80)
        tk.Label(frame,text="Full Name:",font=("Segoe UI",18),bg="white").pack(pady=10)
        name_entry = tk.Entry(frame,font=("Segoe UI",16),width=30)
        name_entry.pack()
        tk.Label(frame,text="Registration Number:",font=("Segoe UI",18),bg="white").pack(pady=10)
        reg_entry = tk.Entry(frame,font=("Segoe UI",16),width=30)
        reg_entry.pack()
        def submit_registration():
            name = name_entry.get().strip()
            regno = reg_entry.get().strip()
            if not name or not regno:
                messagebox.showerror("Input Error","Please enter both Name and Registration Number")
                return
            self.student_info = {"name":name,"regno":regno}
            for subj, file in self.subject_files.items():
                if os.path.exists(file):
                    qs = load_questions(file)
                    self.subject_questions[subj] = random.sample(qs, min(30,len(qs)))
                    self.subject_answers[subj] = [None]*len(self.subject_questions[subj])
                else:
                    messagebox.showerror("File Missing",f"Question file not found: {file}")
            subjects = list(self.subject_questions.keys())
            if not subjects:
                messagebox.showerror("No Questions","No questions loaded!")
                return
            self.selected_subject = subjects[0]
            self.start_time = time.time()
            self.show_exam_interface()
        tk.Button(frame,text="Start Exam",font=("Segoe UI",18,"bold"),bg="#137a13",fg="white",width=20,command=submit_registration).pack(pady=40)

    def show_exam_interface(self):
        self.clear()
        header = tk.Frame(self.master,bg="#137a13",height=60)
        header.pack(fill="x")
        for subj in self.subject_files:
            btn_bg = "#065c06" if subj==self.selected_subject else "#137a13"
            tk.Button(header,text=subj,font=("Segoe UI",12,"bold"),bg=btn_bg,fg="white",relief="flat",command=lambda s=subj:self.switch_subject(s)).pack(side="left",padx=5,pady=8)
        tk.Label(header,text=f"{self.student_info['name']} ({self.student_info['regno']})",font=("Segoe UI",12),fg="white",bg="#137a13").pack(side="right",padx=16)
        calc_btn = tk.Button(header,text="🖩",font=("Segoe UI",22,"bold"),bg="#137a13",fg="white",relief="flat",command=self.show_calculator)
        calc_btn.pack(side="right",padx=5)
        self.timer_lbl = tk.Label(header,text="",font=("Segoe UI",12,"bold"),bg="#137a13",fg="#fff200")
        self.timer_lbl.pack(side="right",padx=16)
        self.qinfo_lbl = tk.Label(header,text="",font=("Segoe UI",11),bg="#137a13",fg="white")
        self.qinfo_lbl.pack(side="right",padx=12)
        if not self.submitted:
            self.show_timer()
        self.update_info()
        main = tk.Frame(self.master,bg="white")
        main.pack(fill="both",expand=True)
        canvas = tk.Canvas(main,bg="white")
        scrollbar = tk.Scrollbar(main,orient="vertical",command=canvas.yview)
        scrollable_frame = tk.Frame(canvas,bg="white")
        scrollable_frame.bind("<Configure>",lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0),window=scrollable_frame,anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left",fill="both",expand=True)
        scrollbar.pack(side="right",fill="y")
        state_qs = self.subject_questions[self.selected_subject]
        state_ans = self.subject_answers[self.selected_subject]
        qidx = self.current_question
        tk.Label(scrollable_frame,text=f"Question {qidx+1} of {len(state_qs)}",font=("Segoe UI",18,"bold"),anchor="w",bg="white",fg="#137a13").pack(pady=(20,10),padx=20,anchor="w")
        q_text = tk.Label(scrollable_frame,text=state_qs[qidx]["question"],font=("Segoe UI",15),wraplength=1000,justify="left",bg="white")
        q_text.pack(anchor="w",padx=20,pady=(0,15))
        ans_val = tk.IntVar(value=state_ans[qidx] if state_ans[qidx] is not None else -1)
        for i,opt in enumerate(state_qs[qidx].get("options",[])):
            def ans_cmd(idx=i):
                if not self.submitted:
                    state_ans[qidx] = idx
                    ans_val.set(idx)
                    self.update_number_buttons()
                    self.update_info()
            rb = tk.Radiobutton(scrollable_frame,text=f"{chr(65+i)}. {opt}",variable=ans_val,value=i,font=("Segoe UI",14),bg="white",anchor="w",justify="left",command=ans_cmd)
            rb.pack(anchor="w",pady=6,padx=20)
        nav = tk.Frame(scrollable_frame,bg="white")
        nav.pack(pady=16)
        tk.Button(nav,text="Previous",font=("Segoe UI",13,"bold"),width=12,bg="#2f89d6",fg="white",command=self.go_prev,state="normal" if qidx>0 else "disabled").pack(side="left",padx=8)
        tk.Button(nav,text="Next",font=("Segoe UI",13,"bold"),width=12,bg="#2f89d6",fg="white",command=self.go_next,state="normal" if qidx<len(state_qs)-1 else "disabled").pack(side="left",padx=8)
        marker = tk.Frame(scrollable_frame,bg="white")
        marker.pack(pady=20,padx=20)
        self.number_buttons = []
        cols = 15
        for i in range(len(state_qs)):
            color = "#dc3545" if state_ans[i] is not None else "#d9d9d9"
            btn = tk.Button(marker,text=str(i+1),font=("Segoe UI",10,"bold"),width=3,bg=color,fg="white",command=lambda idx=i:self.goto_question(idx))
            btn.grid(row=i//cols,column=i%cols,padx=4,pady=4)
            self.number_buttons.append(btn)
        tk.Button(scrollable_frame,text="Submit All Subjects",font=("Segoe UI",13,"bold"),bg="#e67300",fg="white",width=20,command=self.confirm_submit).pack(pady=20)

    def show_calculator(self):
        if self.calc_window and self.calc_window.winfo_exists():
            return
        self.calc_window = tk.Toplevel(self.master)
        self.calc_window.title("Calculator")
        self.calc_window.geometry("300x400")
        self.calc_window.resizable(True,True)
        self.calc_window.attributes("-topmost", True)
        entry = tk.Entry(self.calc_window,font=("Segoe UI",20),borderwidth=5,relief="sunken",justify="right")
        entry.grid(row=0,column=0,columnspan=4,pady=10,padx=10,sticky="we")
        entry.configure(state="readonly")
        def btn_click(val):
            current = entry.get()
            if val=="C":
                entry.configure(state="normal")
                entry.delete(0,"end")
                entry.configure(state="readonly")
            elif val=="⌫":
                entry.configure(state="normal")
                entry.delete(len(current)-1,"end")
                entry.configure(state="readonly")
            elif val=="=":
                try:
                    expression = current.replace("×","*").replace("÷","/")
                    result = str(eval(expression))
                    entry.configure(state="normal")
                    entry.delete(0,"end")
                    entry.insert(0,result)
                    entry.configure(state="readonly")
                except:
                    entry.configure(state="normal")
                    entry.delete(0,"end")
                    entry.insert(0,"Error")
                    entry.configure(state="readonly")
            else:
                entry.configure(state="normal")
                entry.insert("end",val)
                entry.configure(state="readonly")
                
        buttons = [
            ['7','8','9','÷'],
            ['4','5','6','×'],
            ['1','2','3','-'],
            ['C','0','.','+'],
            ['⌫','=']
        ]
        for r,row in enumerate(buttons):
            for c,btn in enumerate(row):
                colspan = 2 if btn=="=" else 1
                width = 5 if btn!="=" else 12
                tk.Button(self.calc_window,text=btn,font=("Segoe UI",14,"bold"),width=width,height=2,command=lambda v=btn: btn_click(v)).grid(row=r+1,column=c,columnspan=colspan,padx=3,pady=3)

    def update_number_buttons(self):
        state_ans = self.subject_answers[self.selected_subject]
        for i,btn in enumerate(self.number_buttons):
            btn.config(bg="#dc3545" if state_ans[i] is not None else "#d9d9d9")

    def switch_subject(self,subject):
        self.selected_subject = subject
        self.current_question = 0
        self.show_exam_interface()

    def go_prev(self):
        if self.current_question>0:
            self.current_question -= 1
            self.show_exam_interface()

    def go_next(self):
        state_qs = self.subject_questions[self.selected_subject]
        if self.current_question<len(state_qs)-1:
            self.current_question +=1
            self.show_exam_interface()

    def goto_question(self,idx):
        self.current_question = idx
        self.show_exam_interface()

    def show_timer(self):
        if not self.submitted:
            elapsed = int(time.time()-self.start_time)
            remaining = self.exam_time - elapsed
            if remaining<0: remaining=0
            mins,secs=divmod(remaining,60)
            self.timer_lbl.config(text=f"Time Left: {mins:02d}:{secs:02d}")
            if remaining>0:
                self.master.after(1000,self.show_timer)
            else:
                self.submit_all()

    def update_info(self):
        state_ans = self.subject_answers[self.selected_subject]
        answered = sum(1 for a in state_ans if a is not None)
        total = len(state_ans)
        self.qinfo_lbl.config(text=f"Answered: {answered} / {total}")

    def confirm_submit(self):
        if messagebox.askyesno("Submit Exam","Do you want to submit all subjects and continue?"):
            self.submit_all()

    def submit_all(self):
        self.submitted = True
        self.results = []
        self.record = {"name":self.student_info["name"],"regno":self.student_info["regno"],"subjects":{}}
        for subj in self.subject_questions:
            qs = self.subject_questions[subj]
            ans = self.subject_answers[subj]
            score = 0
            for i,a in enumerate(ans):
                if a is not None:
                    correct = qs[i].get("answer","")
                    selected = qs[i]["options"][a]
                    try:
                        if float_safe(selected) == float_safe(correct):
                            score += 1
                    except:
                        if str(selected).strip() == str(correct).strip():
                            score += 1
            percent = (score/len(qs)*100) if qs else 0
            self.results.append((subj,score,len(qs),percent))
            self.record["subjects"][subj] = {"score":score,"total":len(qs)}
        save_scores(self.record)
        self.show_results_screen()

    def show_results_screen(self):
        self.clear()
        header = tk.Frame(self.master,bg="#137a13",height=60)
        header.pack(fill="x")
        tk.Label(header,text="KD CBT Examination",font=("Segoe UI",24,"bold"),fg="white",bg="#137a13").pack(side="left",padx=25,pady=12)
        body = tk.Frame(self.master,bg="white")
        body.place(relx=0,rely=0.14,relwidth=1,relheight=0.86)
        tk.Label(body,text="Examination Results",font=("Segoe UI",23,"bold"),fg="#137a13",bg="white").pack(pady=48)
        for subj,score,total,percent in self.results:
            tk.Label(body,text=f"{subj}: {score} / {total}    ({percent:.2f}%)",font=("Segoe UI",17),fg="#065c06",bg="white").pack(pady=12)
        tk.Button(body,text="View Correction",font=("Segoe UI",15,"bold"),bg="#2f89d6",fg="white",width=20,command=self.show_correction_screen).pack(pady=20)
        tk.Button(body,text="Return to Registration",font=("Segoe UI",15,"bold"),bg="#e67300",fg="white",width=20,command=self.show_registration).pack(pady=20)

    def show_correction_screen(self):
        self.clear()
        header = tk.Frame(self.master,bg="#137a13",height=60)
        header.pack(fill="x")
        for subj in self.subject_files:
            btn_bg = "#065c06" if subj==self.selected_subject else "#137a13"
            tk.Button(header,text=subj,font=("Segoe UI",12,"bold"),bg=btn_bg,fg="white",relief="flat",command=lambda s=subj:self.switch_subject_correction(s)).pack(side="left",padx=5,pady=8)
        tk.Label(header,text=f"{self.student_info['name']} ({self.student_info['regno']})",font=("Segoe UI",12),fg="white",bg="#137a13").pack(side="right",padx=16)
        main = tk.Frame(self.master,bg="white")
        main.pack(fill="both",expand=True)
        canvas = tk.Canvas(main,bg="white")
        scrollbar = tk.Scrollbar(main,orient="vertical",command=canvas.yview)
        scrollable_frame = tk.Frame(canvas,bg="white")
        scrollable_frame.bind("<Configure>",lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0),window=scrollable_frame,anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left",fill="both",expand=True)
        scrollbar.pack(side="right",fill="y")
        state_qs = self.subject_questions[self.selected_subject]
        state_ans = self.subject_answers[self.selected_subject]
        for i,q in enumerate(state_qs):
            tk.Label(scrollable_frame,text=f"Q{i+1}: {q['question']}",font=("Segoe UI",15,"bold"),wraplength=1000,justify="left",bg="white",anchor="w").pack(anchor="w",padx=20,pady=(15,5))
            correct_answer = q.get("answer","")
            user_choice = state_ans[i]
            for idx,opt in enumerate(q.get("options",[])):
                is_correct = False
                try:
                    if float_safe(opt) == float_safe(correct_answer):
                        is_correct = True
                except:
                    if str(opt).strip() == str(correct_answer).strip():
                        is_correct = True
                if is_correct:
                    bg_color = "#d4edda"
                elif user_choice == idx and not is_correct:
                    bg_color = "#f8d7da"
                else:
                    bg_color = "white"
                tk.Label(scrollable_frame,text=f"{chr(65+idx)}. {opt}",font=("Segoe UI",14),bg=bg_color,anchor="w",justify="left").pack(anchor="w",padx=40,pady=3)
        tk.Button(scrollable_frame,text="Back to Results",font=("Segoe UI",15,"bold"),bg="#2f89d6",fg="white",width=20,command=self.show_results_screen).pack(pady=20)
        tk.Button(scrollable_frame,text="Return to Registration",font=("Segoe UI",15,"bold"),bg="#e67300",fg="white",width=20,command=self.show_registration).pack(pady=20)

    def switch_subject_correction(self,subject):
        self.selected_subject = subject
        self.show_correction_screen()

    def clear(self):
        for widget in self.master.winfo_children():
            widget.destroy()

if __name__=="__main__":
    root = tk.Tk()
    app = KDCBTApp(root)
    root.mainloop()