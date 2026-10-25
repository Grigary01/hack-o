/* Our adapter for the external NoiseModelling 5.0.1 CLI.
 * Input is our JSON contract, output is receiver / period / LAeq.
 * No acoustic equations are reimplemented here. The external GPL-3.0 engine
 * and its licenses remain in its own distribution (see THIRD_PARTY_NOTICES).
 */
import groovy.json.JsonSlurper
import groovy.json.JsonOutput
import groovy.sql.Sql
import java.sql.Connection

title = 'Adler road-noise adapter'
description = 'Build metric tables, call NoiseModelling, export levels'
inputs = [inputPath: [name:'JSON input', type:String.class],
          nmHome: [name:'NoiseModelling directory', type:String.class],
          outputPath: [name:'JSON output', type:String.class]]
outputs = [result: [name:'Result', type:String.class]]

def exec(Connection connection, input) {
    def data = new JsonSlurper().parse(new File(input.inputPath as String))
    def sql = new Sql(connection)
    sql.execute('CREATE TABLE BUILDINGS(PK INTEGER PRIMARY KEY, THE_GEOM GEOMETRY, HEIGHT DOUBLE)')
    data.buildings.each { b ->
        sql.execute('INSERT INTO BUILDINGS VALUES (?, ST_GEOMFROMTEXT(?,32637),?)',
                    [b.pk as Integer, b.wkt as String, b.height as Double])
    }
    sql.execute('CREATE TABLE RECEIVERS(PK INTEGER PRIMARY KEY, THE_GEOM GEOMETRY)')
    data.receivers.each { r ->
        String wkt = "POINT Z (${r.x} ${r.y} ${r.z})"
        sql.execute('INSERT INTO RECEIVERS VALUES (?, ST_GEOMFROMTEXT(?,32637))', [r.pk as Integer, wkt])
    }
    def columns = []
    ['D','E','N'].each { p ->
        ['LV','MV','HGV','WAV','WBV'].each { v -> columns.add("${v}_${p}".toString()); columns.add("${v}_SPD_${p}".toString()) }
    }
    sql.execute('CREATE TABLE ROADS(PK INTEGER PRIMARY KEY, THE_GEOM GEOMETRY, ' + columns.collect { it+' DOUBLE' }.join(',') + ')')
    String insert = 'INSERT INTO ROADS VALUES (?, ST_GEOMFROMTEXT(?,32637),'+columns.collect{'?'}.join(',')+')'
    data.roads.each { r ->
        sql.execute(insert, [r.pk as Integer, r.wkt as String] + columns.collect{ r.traffic[it] as Double })
    }
    // Engine computes propagation, including building shielding and diffraction.
    def script = new GroovyShell().parse(new File(input.nmHome as String,
            'noisemodelling/wps/NoiseModelling/Noise_level_from_traffic.groovy'))
    script.invokeMethod('exec', [connection, [tableBuilding:'BUILDINGS', tableRoads:'ROADS',
        tableReceivers:'RECEIVERS', confMaxSrcDist:500.0, confReflOrder:1,
        confDiffVertical:true, confDiffHorizontal:true, confThreadNumber:2]] as Object[])
    def levels = sql.rows('SELECT IDRECEIVER, PERIOD, LAEQ FROM RECEIVERS_LEVEL').collect { r ->
        [receiver_id:r.IDRECEIVER, period:r.PERIOD, laeq_db:r.LAEQ]
    }
    new File(input.outputPath as String).text = JsonOutput.toJson(levels)
    return 'Exported '+levels.size()+' receiver-period levels'
}
