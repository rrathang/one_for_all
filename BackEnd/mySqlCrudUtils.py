import pymysql

class mySqlCrudUtils:
    def __init__(self, *args, **kwargs):
        self.host = kwargs.get('host', 'localhost')
        self.user = kwargs.get('user', 'root')
        self.password = kwargs.get('password', 'root')
        self.database = kwargs.get('database')
        self.module_dict = {}

    def getConnection(self):
        connection = pymysql.connect(host=self.host, user=self.user, password=self.password, database=self.database, cursorclass=pymysql.cursors.DictCursor)
        return connection

    def read(self, *args, **kwargs):
        condition = kwargs.get('condition')
        selectColumns = kwargs.get('selectColumns', '*')
        tableName = kwargs.get('tableName', None)
        fetchone = kwargs.get('fetchone', False)
        connection = self.getConnection()

        def buildQueryWithCondition(self, *args, **kwargs):
            condition = kwargs.get('condition', None)
            query = kwargs.get('query', None)
            queryWithCondition = "{0} where {1}".format(query,condition)
            return queryWithCondition

        sqlTemplate = "SELECT {0} FROM {1}.{2}"
        query = sqlTemplate.format(selectColumns,self.database,tableName)
        if condition:
            query = buildQueryWithCondition(self, condition = condition, query = query)
        with connection.cursor() as cursor:
            cursor.execute(query)
            result = None
            if fetchone:
                result = cursor.fetchone()
            else:
                result = cursor.fetchall()
            connection.close()
            return result
        connection.close()

    # update(primaryKey = 'id', primaryKeyValue = 23, UpdateColumnValueDict = updateDict,tableName = 'table1')
    def update(self, *args, **kwargs):
        primaryKey = kwargs.get('primaryKey')
        primaryKeyValue = kwargs.get('primaryKeyValue')
        UpdateColumnValueDict = kwargs.get('UpdateColumnValueDict')
        tableName = kwargs.get('tableName', None)
        connection = self.getConnection()

        if type(primaryKeyValue) != int:
            primaryKeyValue = f'"{primaryKeyValue}"'
        updateList = [f'{key} = "{value}"' for key,value in UpdateColumnValueDict.items()]
        updateValuesStr = ', '.join(updateList)
        query = f'UPDATE {self.database}.{tableName} SET {updateValuesStr} WHERE {primaryKey}={primaryKeyValue}'
        query = query.replace('"now()"', 'now()')
        with connection.cursor() as cursor:
            cursor.execute(query)
            connection.commit()
        connection.close()
    # create(InsertColumnValueDict = updateDict, tableName = 'table1')
    def create(self, *args, **kwargs):
        InsertColumnValueDictList = kwargs.get('InsertColumnValueDict')
        tableName = kwargs.get('tableName', None)
        connection = self.getConnection()

        if type(InsertColumnValueDictList) == dict:
            InsertColumnValueDictList = [InsertColumnValueDictList]
        cursor = connection.cursor()
        for InsertColumnValueDict in InsertColumnValueDictList:
            insertColumns = [insertColumns for insertColumns in InsertColumnValueDict.keys()]
            insertVales = [f'{insertValues}' if type(insertValues) == int else f'"{insertValues}"' for insertValues in InsertColumnValueDict.values()]
            insertColumnsStr = ', '.join(insertColumns)
            insertValesStr = ', '.join(insertVales)
            query = f'INSERT INTO {self.database}.{tableName} ({insertColumnsStr}) VALUES ({insertValesStr})'
            try:
                cursor.execute(query)
            except Exception as e:
                connection.close()
                raise e
            connection.commit()
        connection.close()

    def insertBulk(self, *args, **kwargs):
        insertRows = kwargs.get('insertRows')
        tableName = kwargs.get('tableName', None)
        columns = kwargs.get('columns')
        connection = self.getConnection(self)
        cursor = connection.cursor()
        for row in insertRows:
            values = ''
            for data in row:
                if type(data) == str:
                    values += f'"{data}" '
                if type(data) == float or type(data) == int:
                    values += f'{data} '
                if insertRows[1][-1] != data:
                    values += f','
            query = f'INSERT INTO {self.database}.{tableName} {columns} VALUES ({values})'
            try:
                cursor.execute(query)
            except Exception as e:
                self.connection.close()
                raise e
            connection.commit()
        connection.close()

    def rawQuery(self, *args, **kwargs):
        query = kwargs.get('query', None)
        connection = self.getConnection()
        cursor = connection.cursor()
        cursor.execute(query)
        result = cursor.fetchall()
        connection.close()
        return result

    def close(self, *args, **kwargs):
        self.connection.close()
