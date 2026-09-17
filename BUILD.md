# Collection Dashboard — Full Rebuild Guide
> Django REST Framework (backend) + React + Vite + Tailwind (frontend)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, Django 4.x, Django REST Framework |
| Auth | djangorestframework-simplejwt (JWT) |
| CORS | django-cors-headers |
| Frontend | React 18, Vite, Tailwind CSS |
| HTTP Client | Axios |
| Routing | React Router v6 |
| Data Fetching | TanStack Query (React Query) |
| Icons | Lucide React |
| Charts | Recharts |
| Tables | TanStack Table |
| Date Picker | React Flatpickr |
| Notifications | React Hot Toast |

---

## Project Structure

```
collection-dashboard/
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── dashboard/
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   └── core/
│       ├── models.py
│       ├── serializers.py
│       ├── views.py
│       ├── urls.py
│       └── admin.py
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── api/
        │   ├── axios.js
        │   ├── auth.js
        │   ├── clients.js
        │   ├── debtors.js
        │   ├── cases.js
        │   ├── payments.js
        │   └── reports.js
        ├── components/
        │   ├── layout/
        │   │   ├── Sidebar.jsx
        │   │   ├── Header.jsx
        │   │   └── Layout.jsx
        │   ├── ui/
        │   │   ├── Button.jsx
        │   │   ├── Card.jsx
        │   │   ├── Badge.jsx
        │   │   ├── Modal.jsx
        │   │   ├── DataTable.jsx
        │   │   ├── FilterPanel.jsx
        │   │   ├── StatBar.jsx
        │   │   └── PieChart.jsx
        │   └── forms/
        │       ├── ClientForm.jsx
        │       ├── DebtorForm.jsx
        │       └── CaseForm.jsx
        ├── pages/
        │   ├── Login.jsx
        │   ├── Dashboard.jsx
        │   ├── clients/
        │   │   ├── Clients.jsx
        │   │   └── ClientContacts.jsx
        │   ├── debtors/
        │   │   ├── Debtors.jsx
        │   │   ├── DebtorDetail.jsx
        │   │   └── DebtorContacts.jsx
        │   ├── cases/
        │   │   ├── Cases.jsx
        │   │   ├── FollowUps.jsx
        │   │   ├── BulkFollowUps.jsx
        │   │   ├── CaseGroups.jsx
        │   │   └── PendingPayments.jsx
        │   ├── reports/
        │   │   ├── CaseReport.jsx
        │   │   ├── CollectorReport.jsx
        │   │   ├── DebtorReport.jsx
        │   │   ├── ClientReport.jsx
        │   │   ├── AgencyReport.jsx
        │   │   ├── CollectionsReport.jsx
        │   │   ├── CommissionReport.jsx
        │   │   ├── NewAllocationReport.jsx
        │   │   ├── ReceiptReport.jsx
        │   │   └── ActivityLogs.jsx
        │   └── settings/
        │       ├── ClientAccess.jsx
        │       ├── Users.jsx
        │       └── ...
        ├── hooks/
        │   ├── useAuth.js
        │   └── useDebounce.js
        └── utils/
            ├── formatters.js
            └── constants.js
```

---

## Step 1 — Backend Setup

### 1.1 Create Django project

```bash
mkdir collection-dashboard && cd collection-dashboard
mkdir backend && cd backend
python -m venv venv
source venv/bin/activate
pip install django djangorestframework django-cors-headers djangorestframework-simplejwt
django-admin startproject dashboard .
python manage.py startapp core
```

### 1.2 requirements.txt

```
django>=4.2
djangorestframework>=3.15
django-cors-headers>=4.3
djangorestframework-simplejwt>=5.3
```

### 1.3 dashboard/settings.py

```python
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = 'your-secret-key-here'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'core',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',  # Vite dev server
]
CORS_ALLOW_CREDENTIALS = True

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
```

### 1.4 dashboard/urls.py

```python
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/', include('core.urls')),
]
```

---

## Step 2 — Django Models (core/models.py)

```python
from django.db import models
from django.contrib.auth.models import User


class Client(models.Model):
    CLIENT_TYPE_CHOICES = [
        ('agency','Agency'),('bank','Bank'),('corporate','Corporate'),
        ('education','Education'),('finance','Finance'),('hospital','Hospital'),
        ('hotel','Hotel'),('individual','Individual'),('insurance','Insurance'),
        ('telecommunication','Telecommunication'),
    ]
    STATUS_CHOICES = [('active','Active'),('inactive','Inactive')]

    name           = models.CharField(max_length=200)
    alias_name     = models.CharField(max_length=200, blank=True)
    email          = models.EmailField(blank=True)
    phone          = models.CharField(max_length=50, blank=True)
    mobile         = models.CharField(max_length=50, blank=True)
    contact_person = models.CharField(max_length=200, blank=True)
    client_type    = models.CharField(max_length=30, choices=CLIENT_TYPE_CHOICES, blank=True)
    contract_type  = models.CharField(max_length=100, blank=True)
    address        = models.TextField(blank=True)
    city           = models.CharField(max_length=100, blank=True)
    country        = models.CharField(max_length=100, default='Oman')
    notes          = models.TextField(blank=True)
    status         = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    created_by     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients_created')
    created_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.name


class Debtor(models.Model):
    STATUS_CHOICES = [('active','Active'),('inactive','Inactive')]

    first_name   = models.CharField(max_length=100)
    middle_name  = models.CharField(max_length=100, blank=True)
    last_name    = models.CharField(max_length=100, blank=True)
    is_organization = models.BooleanField(default=False)
    email        = models.EmailField(blank=True)
    phone        = models.CharField(max_length=50, blank=True)
    nationality  = models.CharField(max_length=100, blank=True)
    address      = models.TextField(blank=True)
    country      = models.CharField(max_length=100, blank=True)
    notes        = models.TextField(blank=True)
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    collector    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='debtors_collected')
    created_at   = models.DateTimeField(auto_now_add=True)

    @property
    def name(self):
        return ' '.join(filter(None, [self.first_name, self.middle_name, self.last_name]))

    def __str__(self): return self.name


class Case(models.Model):
    STATUS_CHOICES = [
        ('active','Active'),('broken_promise','Broken Promise'),
        ('contactable','Contactable'),('closed_by_client','Closed by Client request'),
        ('closed','Closed'),
    ]

    case_id         = models.CharField(max_length=60, unique=True, blank=True)
    client          = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='cases')
    debtor          = models.ForeignKey(Debtor, on_delete=models.CASCADE, related_name='cases')
    approved_amount = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    received_amount = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    status          = models.CharField(max_length=30, choices=STATUS_CHOICES, default='active')
    collector       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cases_collected')
    notes           = models.TextField(blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    @property
    def remaining_amount(self):
        return self.approved_amount - self.received_amount

    def save(self, *args, **kwargs):
        if not self.case_id:
            from django.utils import timezone
            now = timezone.now()
            count = Case.objects.count() + 1
            self.case_id = f"CRSS/{now.year}/{now.month:02d}/{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self): return self.case_id


class Payment(models.Model):
    METHOD_CHOICES = [
        ('cash','Cash'),('cheque','Cheque'),('bank_transfer','Bank Transfer'),
        ('online','Online Payment'),('other','Other'),
    ]
    STATUS_CHOICES = [('pending','Pending'),('cleared','Cleared'),('bounced','Bounced')]

    payment_id     = models.CharField(max_length=60, unique=True, blank=True)
    case           = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='payments')
    amount         = models.DecimalField(max_digits=12, decimal_places=3)
    payment_date   = models.DateField()
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='bank_transfer')
    reference_number = models.CharField(max_length=100, blank=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes          = models.TextField(blank=True)
    created_by     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments_created')
    created_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.payment_id


class FollowUp(models.Model):
    FOLLOW_UP_TYPE_CHOICES = [
        ('call','Call'),('email','Email'),('letter','Letter'),
        ('visit','Visit'),('legal','Legal'),('sms','SMS'),('other','Other'),
    ]

    case           = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='follow_ups')
    follow_up_type = models.CharField(max_length=20, choices=FOLLOW_UP_TYPE_CHOICES)
    follow_up_date = models.DateField()
    followed_by    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    case_status    = models.CharField(max_length=30, blank=True)
    notes          = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)


class ActivityLog(models.Model):
    LOG_TYPE_CHOICES = [
        ('login','Login'),('logout','Logout'),('create','Create'),
        ('update','Update'),('delete','Delete'),('export','Export'),
        ('import','Import'),('payment','Payment'),('view','View'),('other','Other'),
    ]

    user       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    log_type   = models.CharField(max_length=20, choices=LOG_TYPE_CHOICES, default='other')
    action     = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
```

---

## Step 3 — Serializers (core/serializers.py)

```python
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Client, Debtor, Case, Payment, FollowUp, ActivityLog


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'full_name', 'is_active']

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__'


class DebtorSerializer(serializers.ModelSerializer):
    name = serializers.ReadOnlyField()

    class Meta:
        model = Debtor
        fields = '__all__'


class CaseSerializer(serializers.ModelSerializer):
    client_name   = serializers.CharField(source='client.name', read_only=True)
    debtor_name   = serializers.CharField(source='debtor.name', read_only=True)
    collector_name = serializers.SerializerMethodField()
    remaining_amount = serializers.ReadOnlyField()

    class Meta:
        model = Case
        fields = '__all__'

    def get_collector_name(self, obj):
        if obj.collector:
            return obj.collector.get_full_name() or obj.collector.username
        return None


class PaymentSerializer(serializers.ModelSerializer):
    case_id      = serializers.CharField(source='case.case_id', read_only=True)
    client_name  = serializers.CharField(source='case.client.name', read_only=True)
    debtor_name  = serializers.CharField(source='case.debtor.name', read_only=True)
    collector_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = '__all__'

    def get_collector_name(self, obj):
        if obj.case.collector:
            return obj.case.collector.get_full_name() or obj.case.collector.username
        return None


class FollowUpSerializer(serializers.ModelSerializer):
    class Meta:
        model = FollowUp
        fields = '__all__'


class ActivityLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = '__all__'

    def get_user_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return None


class DashboardStatsSerializer(serializers.Serializer):
    total_active_cases   = serializers.IntegerField()
    total_approved       = serializers.DecimalField(max_digits=15, decimal_places=3)
    total_received       = serializers.DecimalField(max_digits=15, decimal_places=3)
    total_remaining      = serializers.DecimalField(max_digits=15, decimal_places=3)
    total_clients        = serializers.IntegerField()
    total_debtors        = serializers.IntegerField()
    total_collectors     = serializers.IntegerField()
    cases_by_status      = serializers.ListField()
    recent_payments      = PaymentSerializer(many=True)
```

---

## Step 4 — API Views (core/views.py)

```python
from rest_framework import viewsets, filters, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.db.models import Sum, Count, Q
from .models import Client, Debtor, Case, Payment, FollowUp, ActivityLog
from .serializers import *


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all().order_by('-created_at')
    serializer_class = ClientSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'email', 'phone', 'alias_name']
    ordering_fields = ['name', 'created_at', 'status']

    def get_queryset(self):
        qs = super().get_queryset()
        status_f = self.request.query_params.get('status')
        if status_f:
            qs = qs.filter(status=status_f)
        return qs


class DebtorViewSet(viewsets.ModelViewSet):
    queryset = Debtor.objects.all().order_by('-created_at')
    serializer_class = DebtorSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['first_name', 'last_name', 'email', 'phone']


class CaseViewSet(viewsets.ModelViewSet):
    queryset = Case.objects.select_related('client', 'debtor', 'collector').order_by('-created_at')
    serializer_class = CaseSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['case_id', 'client__name', 'debtor__first_name']

    def get_queryset(self):
        qs = super().get_queryset()
        status_f    = self.request.query_params.get('status')
        collector_f = self.request.query_params.get('collector')
        client_f    = self.request.query_params.get('client')
        if status_f:    qs = qs.filter(status=status_f)
        if collector_f: qs = qs.filter(collector_id=collector_f)
        if client_f:    qs = qs.filter(client_id=client_f)
        return qs


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related('case', 'case__client', 'case__debtor', 'case__collector').order_by('-payment_date')
    serializer_class = PaymentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        date_from = self.request.query_params.get('date_from')
        date_to   = self.request.query_params.get('date_to')
        if date_from: qs = qs.filter(payment_date__gte=date_from)
        if date_to:   qs = qs.filter(payment_date__lte=date_to)
        return qs


class FollowUpViewSet(viewsets.ModelViewSet):
    queryset = FollowUp.objects.select_related('case', 'followed_by').order_by('-follow_up_date')
    serializer_class = FollowUpSerializer


class ActivityLogViewSet(viewsets.ModelViewSet):
    queryset = ActivityLog.objects.select_related('user').order_by('-created_at')
    serializer_class = ActivityLogSerializer
    http_method_names = ['get', 'post']


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.filter(is_active=True).order_by('first_name')
    serializer_class = UserSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    active_cases = Case.objects.exclude(status__in=['closed', 'closed_by_client'])
    agg = active_cases.aggregate(
        total_approved=Sum('approved_amount'),
        total_received=Sum('received_amount'),
    )
    approved  = float(agg['total_approved'] or 0)
    received  = float(agg['total_received'] or 0)

    cases_by_status = []
    for val, label in Case.STATUS_CHOICES:
        count = Case.objects.filter(status=val).count()
        if count:
            cases_by_status.append({'status': val, 'label': label, 'count': count})

    recent_payments = Payment.objects.select_related(
        'case', 'case__client', 'case__debtor', 'case__collector'
    ).order_by('-created_at')[:10]

    return Response({
        'total_active_cases':  active_cases.count(),
        'total_approved':      approved,
        'total_received':      received,
        'total_remaining':     approved - received,
        'total_clients':       Client.objects.filter(status='active').count(),
        'total_debtors':       Debtor.objects.filter(status='active').count(),
        'total_collectors':    User.objects.filter(cases_collected__isnull=False).distinct().count(),
        'cases_by_status':     cases_by_status,
        'recent_payments':     PaymentSerializer(recent_payments, many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)
```

---

## Step 5 — API URLs (core/urls.py)

```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('clients',      views.ClientViewSet)
router.register('debtors',      views.DebtorViewSet)
router.register('cases',        views.CaseViewSet)
router.register('payments',     views.PaymentViewSet)
router.register('follow-ups',   views.FollowUpViewSet)
router.register('activity-logs',views.ActivityLogViewSet)
router.register('users',        views.UserViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', views.dashboard_stats, name='dashboard_stats'),
    path('me/', views.me, name='me'),
]
```

---

## Step 6 — Frontend Setup

```bash
cd collection-dashboard
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
npm install axios react-router-dom @tanstack/react-query lucide-react recharts react-hot-toast flatpickr react-flatpickr
```

### tailwind.config.js

```js
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#2e7d32',
          dark: '#1b5e20',
          light: '#4caf50',
        }
      }
    }
  },
  plugins: [],
}
```

### src/index.css

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer components {
  .btn-primary {
    @apply bg-primary text-white px-4 py-2 rounded-lg font-semibold hover:bg-primary-dark transition-colors text-sm;
  }
  .btn-secondary {
    @apply bg-white text-gray-500 border border-gray-200 px-4 py-2 rounded-lg font-semibold hover:border-gray-400 transition-colors text-sm;
  }
  .card {
    @apply bg-white rounded-xl shadow-sm p-5;
  }
  .input {
    @apply w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-primary transition-colors;
  }
  .select {
    @apply w-full px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-primary bg-white;
  }
  .badge {
    @apply inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold;
  }
}
```

---

## Step 7 — Axios Setup (src/api/axios.js)

```js
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
});

// Attach token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Auto-refresh on 401
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401) {
      try {
        const refresh = localStorage.getItem('refresh_token');
        const { data } = await axios.post('http://localhost:8000/api/auth/refresh/', { refresh });
        localStorage.setItem('access_token', data.access);
        err.config.headers.Authorization = `Bearer ${data.access}`;
        return api(err.config);
      } catch {
        localStorage.clear();
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  }
);

export default api;
```

---

## Step 8 — Auth Hook (src/hooks/useAuth.js)

```js
import { useState, createContext, useContext } from 'react';
import axios from 'axios';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const u = localStorage.getItem('user');
    return u ? JSON.parse(u) : null;
  });

  const login = async (username, password) => {
    const { data } = await axios.post('http://localhost:8000/api/auth/login/', { username, password });
    localStorage.setItem('access_token', data.access);
    localStorage.setItem('refresh_token', data.refresh);
    // fetch user info
    const me = await axios.get('http://localhost:8000/api/me/', {
      headers: { Authorization: `Bearer ${data.access}` }
    });
    localStorage.setItem('user', JSON.stringify(me.data));
    setUser(me.data);
  };

  const logout = () => {
    localStorage.clear();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
```

---

## Step 9 — App Router (src/App.jsx)

```jsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './hooks/useAuth';
import Layout from './components/layout/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Clients from './pages/clients/Clients';
import Debtors from './pages/debtors/Debtors';
import Cases from './pages/cases/Cases';
// import all other pages...

const queryClient = new QueryClient();

function PrivateRoute({ children }) {
  const { user } = useAuth();
  return user ? children : <Navigate to="/login" />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>
              <Route index element={<Dashboard />} />
              <Route path="clients" element={<Clients />} />
              <Route path="debtors" element={<Debtors />} />
              <Route path="cases" element={<Cases />} />
              {/* add all other routes */}
            </Route>
          </Routes>
        </BrowserRouter>
        <Toaster position="top-right" />
      </AuthProvider>
    </QueryClientProvider>
  );
}
```

---

## Step 10 — Layout (src/components/layout/Layout.jsx)

```jsx
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';

export default function Layout() {
  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
```

---

## Step 11 — All API Endpoints Reference

| Method | URL | Description |
|---|---|---|
| POST | `/api/auth/login/` | Login → returns JWT |
| POST | `/api/auth/refresh/` | Refresh access token |
| GET | `/api/me/` | Current user info |
| GET | `/api/dashboard/` | Dashboard stats |
| GET/POST | `/api/clients/` | List / Create clients |
| GET/PUT/DELETE | `/api/clients/{id}/` | Read / Update / Delete client |
| GET/POST | `/api/debtors/` | List / Create debtors |
| GET/PUT/DELETE | `/api/debtors/{id}/` | Read / Update / Delete debtor |
| GET/POST | `/api/cases/` | List / Create cases |
| GET/PUT/DELETE | `/api/cases/{id}/` | Read / Update / Delete case |
| GET/POST | `/api/payments/` | List / Create payments |
| GET/PUT/DELETE | `/api/payments/{id}/` | Read / Update / Delete payment |
| GET/POST | `/api/follow-ups/` | List / Create follow-ups |
| GET/POST | `/api/activity-logs/` | List / Create activity logs |
| GET | `/api/users/` | All users (for dropdowns) |

### Query Params

```
GET /api/cases/?status=active&collector=1&client=2&search=CRSS
GET /api/payments/?date_from=2026-01-01&date_to=2026-12-31
GET /api/clients/?status=active&search=bank
```

---

## Step 12 — Pages to Build

### Priority Order

1. **Login** — JWT form, store tokens, redirect
2. **Dashboard** — stat cards, cases by status pie, recent payments table
3. **Clients** — table with search, add/edit modal, status toggle, delete
4. **Debtors** — table with search, 3-step add wizard, debtor detail page
5. **Cases** — filter panel, colored status rows, add modal
6. **Follow Ups** — date-filtered table
7. **Payments** — pending payments list
8. **Reports** — Cases, Collector, Receipt, Commission, Collections, Agency, Client, Debtor
9. **Activity Logs** — filter by date/user/type, DataTable
10. **Settings** — Client Access, Users, Agencies, Lawyers, etc.

---

## Step 13 — Run Both Servers

### Backend
```bash
cd backend
source venv/bin/activate
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8000
```

### Frontend
```bash
cd frontend
npm run dev
# runs on http://localhost:5173
```

---

## Color Reference (match existing design)

```js
// tailwind.config.js extend colors
colors: {
  primary: { DEFAULT: '#2e7d32', dark: '#1b5e20' },
  sidebar: '#1a1f2e',
  header: '#2e7d32',
}

// Status badge colors
const STATUS_COLORS = {
  active:          'bg-green-100 text-green-700',
  broken_promise:  'bg-yellow-100 text-yellow-700',
  contactable:     'bg-blue-100 text-blue-700',
  closed_by_client:'bg-pink-100 text-pink-700',
  closed:          'bg-red-100 text-red-700',
}
```

---

## Stat Bar Colors (Reports pages)

```js
const STAT_COLORS = {
  teal:    'bg-teal-600',    // Total Cases / unique count
  purple:  'bg-purple-700',  // Collection count
  pink:    'bg-pink-600',    // Total amount
  dpurple: 'bg-violet-800',  // Remaining / commission
}
```

---

## Notes

- All dates: use `react-flatpickr` with `mode: "range"`
- All charts: use `recharts` PieChart
- All tables: client-side search + pagination with TanStack Table
- All modals: use a reusable `<Modal>` component with portal
- Token stored in `localStorage` (`access_token`, `refresh_token`)
- On 401 → auto-refresh → retry → if fail → redirect `/login`

---

## Step 14 — Production Deployment (Railway)

Railway container disks are **ephemeral** — every redeploy, restart or crash
gives the app a fresh filesystem. Nothing durable may live on it. The app is
already stateless in the right ways (Postgres for data, R2 for attachments,
WhiteNoise for static, gunicorn logging to stdout), but only *when the
environment variables below are set*. Every one of them fails open in local
dev, which is why `dashboard/settings.py` refuses to boot when `DJANGO_DEBUG=0`
and any of them is missing.

### 14.1 Required environment variables

| Variable | Value | Missing in production means |
|---|---|---|
| `DJANGO_DEBUG` | `0` | Debug pages leak tracebacks + settings |
| `DATABASE_URL` | auto-injected by Railway Postgres | Silent SQLite on ephemeral disk — **all data lost every redeploy** |
| `REDIS_URL` | auto-injected by Railway Redis | Per-process cache; slow dashboard, no shared sessions |
| `DJANGO_SECRET_KEY` | long random string | Hardcoded dev key — forgeable sessions/tokens |
| `DJANGO_ALLOWED_HOSTS` | `dashboard.tawazonoman.com` | Answers to any Host header |
| `AWS_STORAGE_BUCKET_NAME` | `tawazon-media` | Attachments to ephemeral disk — **uploads lost, DB rows point at nothing** |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | R2 API token pair | Uploads fail |
| `AWS_S3_ENDPOINT_URL` | `https://<account-id>.r2.cloudflarestorage.com` | django-storages talks to real AWS instead of R2 |
| `AWS_S3_CUSTOM_DOMAIN` | `media.tawazonoman.com` | Attachment URLs bypass the CDN domain |
| `RESEND_API_KEY` | from resend.com | Console mail backend — **no client can log into the portal** — and `send_mail()` still reports success. See 14.3 — **required on Railway**, SMTP does not work here |
| `SENTRY_DSN` | from sentry.io | No alerts on 500s, no slow-query list |

Generate a secret key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### 14.2 The startup guard

With `DJANGO_DEBUG=0`, settings.py collects every unsafe fallback and raises
`ImproperlyConfigured` listing all of them at once, rather than booting into a
state that loses data quietly. A deploy that will not start is a five-minute
fix; silent data loss is not recoverable.

To deliberately run a box on the unsafe defaults (a throwaway staging
instance, say), set `DJANGO_ALLOW_UNSAFE_CONFIG=1`.

### 14.3 Outbound mail: Resend, not Zoho SMTP — Railway blocks SMTP outbound

**Confirmed 2026-09-17:** Railway silently blocks outbound SMTP entirely.
Connections to `smtp.zoho.in` on both port 587 (STARTTLS) and port 465
(implicit SSL) hung in `socket.connect()` with no response — not a refusal,
not a Zoho-side block, just a dead connection until it timed out. That's a
platform-level restriction on Railway's egress, and no SMTP configuration
fixes it. (The `django-anymail` runtime dependency, `EMAIL_HOST`/`EMAIL_PORT`/
etc. settings, and the SMTP fallback path in `dashboard/settings.py` all still
exist for running this app on a host that doesn't block SMTP — just not
Railway.)

The fix: send mail over HTTPS instead, which is never blocked. `dashboard/settings.py`
uses **Resend**'s API via `django-anymail` when `RESEND_API_KEY` is set —
falls back to Zoho SMTP if only `EMAIL_HOST_PASSWORD` is set (for non-Railway
hosts), then to the console backend if neither is set. The startup guard
requires one of the two real backends when `DJANGO_DEBUG=0`.

Setup:
1. Create a Resend account (resend.com) → **API Keys** → create one, scoped to
   **Sending access** only.
2. **Domains** → Add Domain → `tawazonoman.com` → Resend shows DNS records to
   add (see 14.4 below) → verify.
3. Set `RESEND_API_KEY` in Railway. `DEFAULT_FROM_EMAIL` stays
   `info@tawazonoman.com` — Resend sends *as* that address once the domain is
   verified; the Zoho mailbox itself is untouched and still receives replies
   normally.

If this app ever runs somewhere that doesn't block SMTP, Zoho SMTP still
works as the fallback — `EMAIL_HOST` follows **the data center the Zoho
account was registered in**, not where users/clients are located (the Tawazon
account is on Zoho India, so `smtp.zoho.in`, regardless of the client being in
Oman), and needs an **app-specific password**, not the account password.

### 14.4 SPF + DKIM (Cloudflare DNS)

Without these, OTP emails are spam-filtered or dropped by the recipient's
provider — and the sending API reports success regardless, because the
message left the sender's servers fine. Symptom is identical to a broken send
path: "the client never got the code", nothing in the logs to explain why.

Two separate senders now share `tawazonoman.com` as the From-domain — Zoho
(inbound mailbox, and SMTP if ever used as the fallback) and Resend (actual
OTP sending on Railway) — both need authorizing in the *same* SPF record, and
each needs its own DKIM record:

- **SPF** — one TXT on the root, both included:
  `v=spf1 include:zohomail.in include:resend.net ~all` (confirm Resend's exact
  include value on their domain-verification page — it's the DNS record
  Resend hands you when you add the domain there). If a TXT SPF record
  already exists, merge into it — two separate SPF records is itself a
  failure, not additive.
- **DKIM** — two separate records, one per sender:
  - Zoho: Zoho Mail admin → Email Authentication → generate key → add the TXT
    record it gives you.
  - Resend: the domain-verification page in the Resend dashboard shows its
    own DKIM TXT record → add it.
- **DMARC** (recommended) — TXT at `_dmarc`: `v=DMARC1; p=none; rua=mailto:info@tawazonoman.com`
  Start at `p=none` and only tighten once the reports come back clean.

Verify before trusting it:

```bash
dig +short TXT tawazonoman.com
dig +short TXT zmail._domainkey.tawazonoman.com
```

### 14.5 Backups — not on by default

Postgres and R2 being managed services protects against the ephemeral disk. It
does **not** protect against a bad migration, a wrong bulk delete, or a
mistaken import. Both need turning on by hand, in their dashboards:

- **Railway Postgres** → the Postgres service → Backups → enable scheduled
  backups, and note the retention window.
- **Cloudflare R2** → the bucket → Settings → enable **object versioning**, so
  an overwritten or deleted attachment is recoverable.

Test the restore path once, before the client has real data in it. An untested
backup is not a backup.

### 14.6 Domain

`tawazonoman.com` is on Cloudflare. Point `dashboard.tawazonoman.com` at the
Railway target with a single CNAME, **DNS-only (grey cloud)** to start — turn
proxying on only after the app is confirmed working, so a proxy
misconfiguration is never in the debugging path.
