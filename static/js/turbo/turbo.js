{% load static %}
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Your Project</title>
    <link rel="stylesheet" type="text/css" href="{% static 'css/style.css' %}">
    <script src="{% static 'js/turbo/turbo.js' %}" defer></script>
</head>
<body>
    {% block content %}
    {% endblock %}
</body>
</html>
