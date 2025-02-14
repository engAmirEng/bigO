class DBRouter:
    stats_db_models_names = ["subscriptionnodeusage"]

    def db_for_read(self, model, **hints):
        if model._meta.model_name in self.stats_db_models_names:
            return "stats"
        return "main"
        # if model._meta.app_label in self.route_app_labels:
        #     return "auth_db"
        # return None

    def db_for_write(self, model, **hints):
        if model._meta.model_name in self.stats_db_models_names:
            return "stats"
        return "main"
        # if model._meta.app_label in self.route_app_labels:
        #     return "auth_db"
        # return None

    def allow_relation(self, obj1, obj2, **hints):
        modelname1 = obj1._meta.model_name
        modelname2 = obj2._meta.model_name
        if modelname1 in self.stats_db_models_names and modelname2 in self.stats_db_models_names:
            return True
        if not (modelname1 in self.stats_db_models_names or modelname2 in self.stats_db_models_names):
            return True
        return False
        # if (
        #     obj1._meta.app_label in self.route_app_labels
        #     or obj2._meta.app_label in self.route_app_labels
        # ):
        #     return True
        # return None

    def allow_migrate(self, db, app_label, *, model_name=None, **hints):
        """
        Make sure the auth and contenttypes apps only appear in the
        'auth_db' database.
        """
        if model_name is None:
            return db == "main"
        if model_name in self.stats_db_models_names:
            return db == "stats"
        return db == "main"
        # if app_label in self.route_app_labels:
        #     return db == "auth_db"
        # return None
