from rest_framework import serializers


class NodeInfoSerializer(serializers.Serializer):
    ip_a = serializers.CharField()
