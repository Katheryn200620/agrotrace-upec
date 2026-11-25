from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from .models import Area

User = get_user_model()
C = {"class": "form-control"}


class IngresoForm(AuthenticationForm):
    username = forms.CharField(label="Usuario", widget=forms.TextInput(attrs={**C, "autofocus": True}))
    password = forms.CharField(label="Contraseña", strip=False, widget=forms.PasswordInput(attrs=C))
    error_messages = {"invalid_login": "Usuario o contraseña incorrectos.",
                      "inactive": "Esta cuenta está desactivada. Comuníquese con el administrador general."}


class CambioClaveForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"


class UsuarioForm(forms.Form):
    """Solo el administrador general crea o modifica cuentas, áreas y permisos."""
    username = forms.CharField(label="Usuario", max_length=150, widget=forms.TextInput(attrs=C))
    first_name = forms.CharField(label="Nombres", max_length=150, widget=forms.TextInput(attrs=C))
    last_name = forms.CharField(label="Apellidos", max_length=150, required=False, widget=forms.TextInput(attrs=C))
    email = forms.EmailField(label="Correo", required=False, widget=forms.EmailInput(attrs=C))
    cargo = forms.CharField(max_length=80, required=False, widget=forms.TextInput(attrs=C))
    es_admin_general = forms.BooleanField(label="Es administrador general", required=False,
                                          widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    area = forms.ModelChoiceField(label="Área de trabajo", queryset=Area.objects.filter(activa=True), required=False,
                                  empty_label="— Seleccione —", widget=forms.Select(attrs={"class": "form-select"}))
    puede_crear = forms.BooleanField(label="Puede crear registros", required=False, initial=True,
                                     widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    puede_editar = forms.BooleanField(label="Puede editar sus registros", required=False, initial=True,
                                      widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    puede_eliminar = forms.BooleanField(label="Puede eliminar sus registros", required=False,
                                        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    password1 = forms.CharField(label="Contraseña", required=False, widget=forms.PasswordInput(attrs=C))
    password2 = forms.CharField(label="Repita la contraseña", required=False, widget=forms.PasswordInput(attrs=C))

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)
        if usuario is None:
            self.fields["password1"].required = self.fields["password2"].required = True
        else:
            self.fields["password1"].help_text = "Déjela vacía para no cambiarla."

    def clean_username(self):
        u = self.cleaned_data["username"].strip()
        qs = User.objects.filter(username__iexact=u)
        if self.usuario:
            qs = qs.exclude(pk=self.usuario.pk)
        if qs.exists():
            raise forms.ValidationError("Ese usuario ya existe.")
        return u

    def clean(self):
        d = super().clean()
        if not d.get("es_admin_general") and not d.get("area"):
            self.add_error("area", "Un operador debe tener un área de trabajo.")
        p1, p2 = d.get("password1"), d.get("password2")
        if p1 or p2:
            if p1 != p2:
                self.add_error("password2", "Las contraseñas no coinciden.")
            else:
                try:
                    password_validation.validate_password(p1, self.usuario)
                except forms.ValidationError as e:
                    self.add_error("password1", e)
        return d
